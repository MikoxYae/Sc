"""Telegram control for Sc. Run: python Miko.py"""
import asyncio
import json
import html
import io
import logging
import re
import sys
import tempfile
import time
from PIL import Image
from pathlib import Path
from urllib.parse import urlparse, urljoin, urlunparse
import requests
from bs4 import BeautifulSoup
from sc import fetch, HEADERS

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

import config
from sc import safe_url, make_pdf
from site_adapters import is_mangadass, discover_mangadass, extract_number

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
LOG = logging.getLogger('Sc')
BUSY = asyncio.Lock()
ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / 'data' / 'settings.json'

def load_data():
    try:
        data = json.loads(DATA_FILE.read_text(encoding='utf-8'))
        return {'admins': [int(x) for x in data.get('admins', [])], 'start_pic': data.get('start_pic'), 'settings_pic': data.get('settings_pic'), 'pdf_pic': data.get('pdf_pic'), 'rename_format': data.get('rename_format', '{title} - Chapter {chapter}'), 'caption_style': data.get('caption_style','bold')}
    except (OSError, ValueError, TypeError):
        return {'admins': [], 'start_pic': None, 'settings_pic': None, 'pdf_pic': None, 'rename_format': '{title} - Chapter {chapter}', 'caption_style':'bold'}

DATA = load_data()

def save_data():
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = DATA_FILE.with_suffix('.tmp')
    temp.write_text(json.dumps(DATA, indent=2), encoding='utf-8')
    temp.replace(DATA_FILE)

def is_owner(user):
    return bool(user and user.id == int(config.OWNER_ID))

def allowed(user):
    return bool(user and (is_owner(user) or user.id in DATA['admins']))

# Telegram supports Unicode small-cap characters in text and button labels.
# Characters without a standard small-cap equivalent remain unchanged.
_SMALL_CAPS = str.maketrans({
    'a':'ᴀ','b':'ʙ','c':'ᴄ','d':'ᴅ','e':'ᴇ','f':'ғ','g':'ɢ',
    'h':'ʜ','i':'ɪ','j':'ᴊ','k':'ᴋ','l':'ʟ','m':'ᴍ','n':'ɴ',
    'o':'ᴏ','p':'ᴘ','q':'ǫ','r':'ʀ','s':'s','t':'ᴛ','u':'ᴜ',
    'v':'ᴠ','w':'ᴡ','x':'x','y':'ʏ','z':'ᴢ',
})

def smallcaps(value):
    """Apply readable Unicode small caps while preserving URLs, IDs and commands."""
    return str(value).lower().translate(_SMALL_CAPS)

def ui_text(value):
    """Transform visible text, preserving HTML tags and code/URL spans."""
    pieces = re.split(r'(<[^>]+>|https?://\S+|/\w+|\b\d+\b)', str(value))
    return ''.join(part if (part.startswith('<') or part.startswith('http') or part.startswith('/') or part.isdecimal()) else smallcaps(part) for part in pieces)

def keyboard(rows):
    return InlineKeyboardMarkup([[InlineKeyboardButton(label if str(label).isdecimal() else smallcaps(label), callback_data=key) for label,key in row] for row in rows])

HOME_KB = keyboard([[('Settings','settings'),('Close','close')]])
SETTINGS_KB = keyboard([[('Admin','admins'),('Pictures','pictures')], [('PDF Options','pdf_options'),('Back','home')], [('Close','close')]])
PDF_KB = keyboard([[('PDF Picture','pdf_pic'),('Rename Format','rename_format')], [('Caption Style','caption_style'),('Back','settings')], [('Close','close')]])
STYLE_KB = keyboard([[('Bold','style:bold'),('Underline','style:underline')], [('Spoiler','style:spoiler'),('Plain','style:plain')], [('Back','pdf_options'),('Close','close')]])
ADMINS_KB = keyboard([[('Add Admin','admin_add'),('Remove Admin','admin_remove')], [('List Admins','admin_list'),('Back','settings')], [('Close','close')]])
PICTURES_KB = keyboard([[('Start Picture','pic_start'),('Settings Picture','pic_settings')], [('Use Same Picture','pic_same'),('Back','settings')], [('Close','close')]])

def card(title, description, details=None):
    # Telegram supports HTML bold and blockquote, not arbitrary custom fonts.
    lines = [f'<b>{html.escape(smallcaps(title))}</b>', '', f'<blockquote>{html.escape(ui_text(description))}</blockquote>']
    if details:
        lines.extend(['', ui_text(details)])
    return '\n'.join(lines)

def text_for(page):
    if page == 'home':
        return card('SC | MANGA TO PDF', 'Send a chapter URL to create a PDF from original-quality images.', '<b>Commands</b>\n<code>/start  /settings  /status  /cancel  /help</code>')
    if page == 'settings':
        return card('BOT SETTINGS', 'Select a section below. Saved changes take effect immediately.')
    if page == 'admins':
        return card('ADMIN', 'Add, remove or review administrators. Only the owner can change admin access.')
    if page == 'pdf_options':
        return card('PDF OPTIONS', 'Set a PDF document thumbnail, filename template and Telegram caption style.', '<b>Filename:</b> <code>' + html.escape(DATA.get('rename_format','{title} - Chapter {chapter}')) + '.pdf</code>\n<b>Caption:</b> ' + html.escape(DATA.get('caption_style','bold')))
    if page == 'pdf_pic':
        return card('PDF PICTURE', 'Send a photo for the PDF document thumbnail. It will appear inside the document card when supported by Telegram. No separate photo will be sent.')
    if page == 'rename_format':
        return card('RENAME FORMAT', 'Send a filename template using {title} and {chapter}. Example: {title} - Chapter {chapter}. Do not include .pdf. Your message will be deleted.')
    if page == 'caption_style':
        return card('CAPTION STYLE', 'Choose Telegram caption formatting. Bold, underline and spoiler apply to the document caption, not the filename.')
    if page == 'pictures':
        return card('PICTURE SETTINGS', 'Choose a menu picture to update, or use the same picture for both menus.')
    if page == 'admin_list':
        ids = DATA['admins']
        listing = '\n'.join(f'<code>{x}</code>' for x in ids) if ids else 'No administrators added.'
        return card('ADMIN LIST', f'{len(ids)} administrator(s) registered.', listing)
    if page == 'admin_remove':
        return card('REMOVE ADMIN', 'Select an administrator ID below to revoke access.')
    if page == 'admin_add':
        return card('ADD ADMIN', 'Send the numeric Telegram user ID in this private chat. The message will be deleted after processing, and the menu will return automatically.', '<b>Use Cancel to stop.</b>')
    if page in ('pic_start', 'pic_settings'):
        name = 'START' if page == 'pic_start' else 'SETTINGS'
        return card(f'SET {name} PICTURE', 'Send a Telegram photo here. The photo will be saved, your message deleted, and the menu restored.', '<b>Use Cancel to stop.</b>')
    return card('SC BOT', 'Choose an option.')

def kb_for(page):
    if page == 'home': return HOME_KB
    if page == 'settings': return SETTINGS_KB
    if page == 'pdf_options': return PDF_KB
    if page == 'caption_style': return STYLE_KB
    if page in ('pdf_pic','rename_format'): return keyboard([[('Cancel','pdf_options'),('Back','pdf_options')]])
    if page == 'admins': return ADMINS_KB
    if page == 'pdf_options':
        return card('PDF OPTIONS', 'Set a PDF document thumbnail, filename template and Telegram caption style.', '<b>Filename:</b> <code>' + html.escape(DATA.get('rename_format','{title} - Chapter {chapter}')) + '.pdf</code>\n<b>Caption:</b> ' + html.escape(DATA.get('caption_style','bold')))
    if page == 'pdf_pic':
        return card('PDF PICTURE', 'Send a photo for the PDF document thumbnail. It will appear inside the document card when supported by Telegram. No separate photo will be sent.')
    if page == 'rename_format':
        return card('RENAME FORMAT', 'Send a filename template using {title} and {chapter}. Example: {title} - Chapter {chapter}. Do not include .pdf. Your message will be deleted.')
    if page == 'caption_style':
        return card('CAPTION STYLE', 'Choose Telegram caption formatting. Bold, underline and spoiler apply to the document caption, not the filename.')
    if page == 'pictures': return PICTURES_KB
    if page == 'admin_list': return keyboard([[('Back','admins'),('Close','close')]])
    if page == 'admin_remove':
        rows = [[(str(x),f'remove:{x}')] for x in DATA['admins']]
        rows += [[('Back','admins'),('Close','close')]]
        return keyboard(rows)
    return keyboard([[('Cancel','admins' if page == 'admin_add' else 'pictures'),('Back','admins' if page == 'admin_add' else 'pictures')]])

async def show(context, chat_id, page, message=None):
    pic = DATA['start_pic'] if page == 'home' else DATA['settings_pic'] or DATA['start_pic']
    if page == 'home': pic = DATA['start_pic']
    body, buttons = text_for(page), kb_for(page)
    if message:
        try:
            if pic:
                if message.photo:
                    if message.photo[-1].file_id != pic:
                        from telegram import InputMediaPhoto
                        return await message.edit_media(InputMediaPhoto(media=pic, caption=body, parse_mode='HTML'), reply_markup=buttons)
                    return await message.edit_caption(caption=body, parse_mode='HTML', reply_markup=buttons)
                await message.delete()
            else:
                if message.photo:
                    await message.delete()
                else:
                    await message.edit_text(body, parse_mode='HTML', reply_markup=buttons)
                    return message
        except Exception:
            LOG.debug('Could not edit menu; sending replacement', exc_info=True)
    if pic:
        return await context.bot.send_photo(chat_id, photo=pic, caption=body, parse_mode='HTML', reply_markup=buttons)
    return await context.bot.send_message(chat_id, body, parse_mode='HTML', reply_markup=buttons)

async def settings(update, context):
    if not allowed(update.effective_user): return
    if update.effective_chat.type != 'private':
        await update.effective_message.reply_text(smallcaps('Open the bot in private chat to manage settings.'))
        return
    context.user_data.pop('pending', None)
    await show(context, update.effective_chat.id, 'settings')

async def callback(update, context):
    q = update.callback_query
    if not allowed(q.from_user):
        await q.answer(smallcaps('Access denied. Owner or administrator access required.'), show_alert=True); return
    if q.message.chat.type != 'private':
        await q.answer(smallcaps('Use the bot in private chat.'), show_alert=True); return
    key = q.data
    if not is_owner(q.from_user) and (key.startswith('admin_') or key.startswith('remove:') or key.startswith('pic_') or key == 'pictures' or key in ('pdf_pic','rename_format','caption_style') or key.startswith('style:')):
        await q.answer(smallcaps('Owner only.'), show_alert=True); return
    await q.answer()
    if key == 'job_cancel':
        stopped = await stop_job(context)
        await q.message.edit_text(card('CANCELLING', 'Stopping the current chapter task.' if stopped else 'No active download.'), parse_mode='HTML')
        return
    if key == 'retry_failed':
        retry_items = context.user_data.get('last_failed_chapters', [])
        if BUSY.locked():
            await q.message.edit_text(card('BUSY', 'Wait for the current batch to finish.'), parse_mode='HTML')
            return
        if not retry_items:
            await q.message.edit_text(card('NO FAILED CHAPTERS', 'There are no failed chapters to retry.'), parse_mode='HTML')
            return
        context.user_data['last_failed_chapters'] = []
        await run_chapter_batch(update, context, retry_items, [], q.message.message_id)
        return
    if key == 'range_select':
        context.user_data['pending'] = 'chapter_range'
        context.user_data['range_message_id'] = q.message.message_id
        await show_range_prompt(context, q.message.chat_id, q.message)
        return
    if key.startswith('chapter_page:'):
        await show_chapter_page(context, q.message.chat_id, int(key.split(':')[1]), q.message)
        return
    if key == 'close':
        context.user_data.pop('pending', None)
        try: await q.message.delete()
        except Exception: pass
        return
    if key.startswith('style:'):
        style = key.split(':',1)[1]
        if style in ('bold','underline','spoiler','plain'):
            DATA['caption_style'] = style; save_data()
        await show(context, q.message.chat_id, 'pdf_options', q.message); return
    if key == 'pic_same':
        if DATA['start_pic']:
            DATA['settings_pic'] = DATA['start_pic']; save_data()
        await show(context, q.message.chat_id, 'pictures', q.message); return
    if key.startswith('remove:'):
        try: uid = int(key.split(':',1)[1])
        except ValueError: return
        if uid in DATA['admins']:
            DATA['admins'].remove(uid); save_data()
        await show(context, q.message.chat_id, 'admin_remove', q.message); return
    if key in ('admin_add','pic_start','pic_settings','pdf_pic','rename_format'):
        context.user_data['pending'] = key
        context.user_data['menu_id'] = q.message.message_id
    else:
        context.user_data.pop('pending', None)
    if key in ('home','settings','admins','pictures','admin_add','admin_remove','admin_list','pic_start','pic_settings','pdf_options','pdf_pic','rename_format','caption_style'):
        rendered = await show(context, q.message.chat_id, key, q.message)
        if key in ('admin_add','pic_start','pic_settings','pdf_pic','rename_format') and rendered:
            context.user_data['menu_id'] = rendered.message_id

async def private_input(update, context):
    if not allowed(update.effective_user) or update.effective_chat.type != 'private': return False
    pending = context.user_data.get('pending')
    if not pending: return False
    if pending == 'chapter_range':
        pass
    elif not is_owner(update.effective_user): return False
    if pending == 'chapter_range':
        raw = (update.effective_message.text or '').strip()
        try: await update.effective_message.delete()
        except Exception: pass
        m = re.fullmatch(r'(\d+)\s*-\s*(\d+)', raw)
        chapters = context.user_data.get('discovered_chapters', {})
        if not m or int(m.group(1)) > int(m.group(2)) or int(m.group(2))-int(m.group(1))+1 > 100:
            await context.bot.send_message(update.effective_chat.id, card('INVALID RANGE', 'Send a range such as 1-20 (maximum 100 chapters).'), parse_mode='HTML')
            return True
        a,b = map(int,m.groups())
        selected = [(str(i), chapters[str(i)]) for i in range(a,b+1) if str(i) in chapters]
        missing = [i for i in range(a,b+1) if str(i) not in chapters]
        if not selected:
            await context.bot.send_message(update.effective_chat.id, card('NO CHAPTERS', 'No discovered chapters match your range.'), parse_mode='HTML')
            return True
        context.user_data.pop('pending', None)
        await run_chapter_batch(update, context, selected, missing, context.user_data.pop('range_message_id', None))
        return True
    if pending == 'admin_add':
        raw = (update.effective_message.text or '').strip()
        try: await update.effective_message.delete()
        except Exception: pass
        if not raw.isdecimal() or not (1 <= int(raw) < 10**16):
            await context.bot.send_message(update.effective_chat.id, card('INVALID USER ID', 'Send a numeric Telegram user ID or press Cancel.'), parse_mode='HTML')
            return True
        uid = int(raw)
        if uid != int(config.OWNER_ID) and uid not in DATA['admins']:
            DATA['admins'].append(uid); save_data()
        page = 'admins'
    elif pending == 'rename_format':
        raw = (update.effective_message.text or '').strip()
        try: await update.effective_message.delete()
        except Exception: pass
        if not valid_template(raw):
            await context.bot.send_message(update.effective_chat.id, card('INVALID FORMAT', 'Use {title} and/or {chapter}; maximum 100 characters. No paths or HTML.'), parse_mode='HTML')
            return True
        DATA['rename_format'] = raw; save_data()
        page = 'pdf_options'
    elif pending in ('pic_start','pic_settings','pdf_pic'):
        if not update.effective_message.photo:
            await update.effective_message.reply_text(smallcaps('Please send a photo, or press Cancel.'))
            return True
        DATA['start_pic' if pending == 'pic_start' else 'settings_pic' if pending == 'pic_settings' else 'pdf_pic'] = update.effective_message.photo[-1].file_id
        save_data()
        try: await update.effective_message.delete()
        except Exception: pass
        page = 'pdf_options' if pending == 'pdf_pic' else 'pictures'
    else: return False
    context.user_data.pop('pending', None)
    menu_id = context.user_data.get('menu_id')
    menu = None
    if menu_id:
        try:
            menu = await context.bot.edit_message_reply_markup(update.effective_chat.id, menu_id, reply_markup=None)
        except Exception: pass
    await show(context, update.effective_chat.id, page, menu)
    return True

async def photo_input(update, context):
    await private_input(update, context)



def owner(update: Update) -> bool:
    return allowed(update.effective_user)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner(update):
        await update.effective_message.reply_text(card('ACCESS DENIED', 'This action requires owner or administrator access.'), parse_mode='HTML')
        return
    await show(context, update.effective_chat.id, 'home')


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if owner(update):
        await update.effective_message.reply_text(
            card('BOT STATUS', 'A chapter is currently being processed.') if BUSY.locked()
            else card('BOT STATUS', 'Ready for a chapter URL.'),
            parse_mode='HTML',
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner(update):
        return
    if await stop_job(context):
        await update.effective_message.reply_text(smallcaps('Cancellation requested.'))
    else:
        await update.effective_message.reply_text(smallcaps('No active job.'))


def valid_template(value):
    if not value or len(value) > 100 or '/' in value or "\\" in value or '<' in value or '>' in value:
        return False
    return not re.search(r'\{(?!title\}|chapter\})[^}]*\}|\{|\}', value.replace('{title}','').replace('{chapter}','')) and ('{title}' in value or '{chapter}' in value)

def filename_for(title, chapter, part=None):
    title = re.sub(r'[\x00-\x1f<>:"/\\|?*]', ' ', title).strip(' .')[:95] or 'Manga'
    chapter = re.sub(r'[^0-9A-Za-z._-]', '', str(chapter))[:25] or '1'
    fmt = DATA.get('rename_format', '{title} - Chapter {chapter}')
    if not valid_template(fmt): fmt = '{title} - Chapter {chapter}'
    name = fmt.replace('{title}',title).replace('{chapter}',chapter).strip(' .')[:155]
    if part: name += f' - Part {part[0]} of {part[1]}'
    return name + '.pdf'

def chapter_info(url, meta):
    parsed = urlparse(url)
    slug = parsed.path.strip('/').split('/')
    chapter_slug = slug[-1] if slug else 'chapter-1'
    match = re.search(r'chapter[-_ ]*([0-9]+(?:[._-][0-9]+)?)', chapter_slug, re.I)
    chapter = match.group(1).replace('_','.') if match else '1'
    manga_slug = slug[-2] if len(slug) > 1 else 'manga'
    title = manga_slug.replace('-',' ').replace('_',' ').title()
    return title, chapter

def caption_for(filename):
    label = html.escape(filename)
    style = DATA.get('caption_style','bold')
    tag = {'bold':'b','underline':'u','spoiler':'tg-spoiler'}.get(style)
    return f'<{tag}>{label}</{tag}>' if tag else label

def progress_text(stage, completed, total, elapsed, detail='', title='Detecting title', chapter='?'):
    total = max(1, total)
    pct = min(100, round(completed / total * 100))
    bars = min(12, round(pct * 12 / 100))
    bar = '━' * bars + '─' * (12-bars)
    return (f'<b>{html.escape(smallcaps("CHAPTER PROCESS"))}</b>\n\n'
            f'<b>{html.escape(smallcaps("Manga"))}:</b> {html.escape(title)}\n'
            f'<b>{html.escape(smallcaps("Chapter"))}:</b> {html.escape(str(chapter))}\n\n'
            f'<b>{html.escape(smallcaps(stage))}</b>\n'
            f'<code>{bar}</code> <b>{pct}%</b>\n'
            f'<b>{completed}/{total}</b> {smallcaps("pages")}  |  '
            f'<b>{smallcaps("Elapsed")}:</b> {int(elapsed)}s\n\n'
            f'{html.escape(smallcaps(detail[:160]))}')

def progress_keyboard():
    return keyboard([[('Cancel Download', 'job_cancel')]])

async def stop_job(context):
    context.application.bot_data['cancel_requested'] = True
    proc = context.application.bot_data.get('process')
    if proc and proc.returncode is None:
        proc.terminate()
        return True
    return False

async def prepare_document_thumbnail(bot, file_id):
    """Create a fresh JPEG upload; Telegram thumbnails cannot reuse file IDs.

    Telegram Bot API: JPEG, max 320x320 pixels, under 200 KB.
    """
    remote = await bot.get_file(file_id)
    raw = io.BytesIO()
    await remote.download_to_memory(raw)
    raw.seek(0)
    with Image.open(raw) as source:
        image = source.convert('RGB')
        image.thumbnail((320, 320), Image.Resampling.LANCZOS)
        for quality in (85, 70, 55, 40):
            out = io.BytesIO()
            image.save(out, format='JPEG', quality=quality, optimize=True)
            if out.tell() < 190_000:
                return out.getvalue()
    raise ValueError('Could not compress document thumbnail under 200 KB')


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner(update):
        await update.effective_message.reply_text(card('ACCESS DENIED', 'Owner or administrator access is required.'), parse_mode='HTML')
        return
    if await private_input(update, context):
        return
    url = (update.effective_message.text or '').strip()
    if not re.fullmatch(r'https?://\S+', url):
        await update.effective_message.reply_text(smallcaps('Send a single http(s) chapter URL.'))
        return
    try:
        safe_url(url)
    except ValueError as exc:
        await update.effective_message.reply_text(smallcaps('Invalid URL: ') + str(exc))
        return
    if BUSY.locked():
        await update.effective_message.reply_text(smallcaps('Already processing a chapter. Try again later.'))
        return
    # Manga landing URLs open chapter discovery rather than starting a PDF.
    if not chapter_number(url):
        await discover_manga(update, context, url)
        return
    async with BUSY:
        context.application.bot_data['cancel_requested'] = False
        await process_one(update, context, url)


async def process_one(update, context, url, progress_message=None, batch_mode=False):
        started = time.monotonic()
        job_title, job_chapter = chapter_info(url, {})
        msg = progress_message or await update.effective_message.reply_text(progress_text('Detecting chapter',0,1,0,title=job_title,chapter=job_chapter), parse_mode='HTML',reply_markup=progress_keyboard())
        with tempfile.TemporaryDirectory(prefix='sc_') as tmp:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(ROOT / 'sc.py'), url, '--output', tmp,
                '--max-pages', str(config.MAX_PAGES),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                cwd=str(ROOT),
            )
            context.application.bot_data['process'] = proc
            state = {'stage':'Detecting chapter', 'completed':0, 'total':1, 'detail':'', 'title':job_title, 'chapter':job_chapter}
            lines = []
            async def reader():
                while True:
                    raw = await proc.stdout.readline()
                    if not raw: break
                    line = raw.decode('utf-8',errors='replace').strip()
                    if not line: continue
                    LOG.info('SCRAPER: %s',line)
                    lines.append(line)
                    if len(lines)>150: lines.pop(0)
                    if line.startswith('Title:'):
                        found = line.partition(':')[2].strip()
                        if found and found.lower() not in ('chapter', 'untitled'):
                            # Prefer URL manga title when page title includes site branding.
                            state['title'] = job_title if len(found)>115 else found
                    if line.startswith('Image references:'):
                        try: state['total'] = min(int(line.split(':',1)[1].strip()),int(config.MAX_PAGES))
                        except ValueError: pass
                        state['stage']='Downloading images'
                    elif line.startswith('Downloading page '):
                        state['stage']='Downloading images'
                    elif line.startswith('Saving page '):
                        state['stage']='Saving original images'
                    elif line.startswith('[') and '] Saved' in line:
                        m=re.match(r'\[(\d+)/(\d+)\]',line)
                        if m:
                            state['completed']=int(m.group(1)); state['total']=int(m.group(2))
                        state['stage']='Downloading images'
                    elif line.startswith('Building PDF'):
                        state['stage']='Building PDF'; state['completed']=state['total']
                    state['detail']=line
                await proc.wait()
            task=asyncio.create_task(reader())
            try:
                while not task.done():
                    try: await asyncio.wait_for(asyncio.shield(task),timeout=12)
                    except asyncio.TimeoutError: pass
                    elapsed=time.monotonic()-started
                    if elapsed>900: raise asyncio.TimeoutError()
                    try:
                        await msg.edit_text(progress_text(state['stage'],state['completed'],state['total'],elapsed,state['detail'],state['title'],state['chapter']),parse_mode='HTML',reply_markup=progress_keyboard())
                    except Exception: LOG.debug('Progress edit skipped',exc_info=True)
                await task
                if proc.returncode in (-15, -9):
                    await msg.edit_text(card('CANCELLED','Chapter download stopped.'),parse_mode='HTML')
                    return
            except asyncio.TimeoutError:
                proc.kill(); await proc.wait(); task.cancel()
                await msg.edit_text(card('TIMEOUT','Processing exceeded 15 minutes.'),parse_mode='HTML')
                return
            finally:
                context.application.bot_data.pop('process',None)
            pdf=Path(tmp)/'chapter.pdf'
            if proc.returncode or not pdf.is_file():
                details='\n'.join(lines)[-2200:]
                await msg.edit_text(card('PDF FAILED','Check scraper output below.', '<pre>'+html.escape(details)+'</pre>'),parse_mode='HTML')
                return
            meta_file=Path(tmp)/'metadata.json'
            try: meta=json.loads(meta_file.read_text())
            except (ValueError,OSError): meta={}
            title,chapter=chapter_info(url,meta)
            limit_bytes=int(min(float(getattr(config,'MAX_PDF_MB',48)),48)*1048576)
            if limit_bytes<1048576:
                await msg.edit_text(card('CONFIG ERROR','MAX_PDF_MB must be at least 1.'),parse_mode='HTML'); return
            parts=[pdf]
            if pdf.stat().st_size>limit_bytes:
                await msg.edit_text(progress_text('Splitting PDF',state['total'],state['total'],time.monotonic()-started,title=state['title'],chapter=state['chapter']),parse_mode='HTML')
                images=sorted(p for p in (Path(tmp)/'images').iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png'))
                if not images:
                    await msg.edit_text(card('SPLIT FAILED','No saved images available.'),parse_mode='HTML'); return
                generated=[]
                def split_pages(pages):
                    part=Path(tmp)/f'part_{len(generated)+1:04d}.pdf'
                    make_pdf(pages,part)
                    if part.stat().st_size<=limit_bytes:
                        generated.append(part); return
                    part.unlink(missing_ok=True)
                    if len(pages)==1: raise ValueError('One page exceeds the upload limit.')
                    middle=len(pages)//2
                    split_pages(pages[:middle]); split_pages(pages[middle:])
                try: await asyncio.to_thread(split_pages,images)
                except Exception as exc:
                    await msg.edit_text(card('SPLIT FAILED',str(exc)),parse_mode='HTML'); return
                parts=generated
            thumbnail_bytes = None
            if DATA.get('pdf_pic'):
                try:
                    thumbnail_bytes = await prepare_document_thumbnail(context.bot, DATA['pdf_pic'])
                except Exception:
                    LOG.warning('Thumbnail preparation failed; sending PDF without thumbnail', exc_info=True)
            try:
                for index,part in enumerate(parts,1):
                    await msg.edit_text(progress_text('Uploading PDF',index-1,len(parts),time.monotonic()-started,title=state['title'],chapter=state['chapter']),parse_mode='HTML')
                    filename=filename_for(title,chapter,(index,len(parts)) if len(parts)>1 else None)
                    with part.open('rb') as f:
                        kwargs = dict(document=f, filename=filename, caption=caption_for(filename),
                                      parse_mode='HTML', read_timeout=180, write_timeout=180)
                        if thumbnail_bytes:
                            thumbnail = io.BytesIO(thumbnail_bytes)
                            thumbnail.name = 'thumbnail.jpg'
                            kwargs['thumbnail'] = thumbnail
                        await update.effective_message.reply_document(**kwargs)
                pages = len([p for p in (Path(tmp)/'images').iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png')])
                size_mb = sum(part.stat().st_size for part in parts) / 1048576
                summary = (f'<b>{smallcaps("Manga")}:</b> {html.escape(title)}\n'
                           f'<b>{smallcaps("Chapter")}:</b> {html.escape(str(chapter))}\n'
                           f'<b>{smallcaps("Pages")}:</b> {pages}\n'
                           f'<b>{smallcaps("PDF files delivered")}:</b> {len(parts)}\n'
                           f'<b>{smallcaps("Total size")}:</b> {size_mb:.1f} MB\n'
                           f'<b>{smallcaps("Total time")}:</b> {format_duration(time.monotonic()-started)}')
                if not batch_mode:
                    await msg.edit_text(f'<b>{smallcaps("COMPLETED")}</b>\n\n{summary}',parse_mode='HTML')
                return {'chapter':chapter,'pages':pages,'files':len(parts),'bytes':sum(part.stat().st_size for part in parts)}
            except Exception:
                LOG.exception('Telegram upload failed')
                await msg.edit_text(card('UPLOAD FAILED','PDF generated but upload failed. Check VPS logs.'),parse_mode='HTML')




def chapter_number(url):
    return extract_number(url)


def discover_sync(url):
    safe_url(url)
    with requests.Session() as session:
        session.headers.update(HEADERS)
        response = fetch(session, url, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        heading = soup.select_one('h1')
        title = heading.get_text(' ', strip=True) if heading else urlparse(url).path.strip('/').split('/')[-1].replace('-', ' ').title()
        root_path = urlparse(response.url).path.rstrip('/') + '/'
        chapters = discover_mangadass(response.text, response.url) if is_mangadass(response.url) else {}
        for link in soup.select('a[href]'):
            target = urljoin(response.url, link.get('href', ''))
            parsed = urlparse(target)
            if parsed.netloc != urlparse(response.url).netloc:
                continue
            if not parsed.path.startswith(root_path):
                continue
            number = chapter_number(target)
            if number:
                chapters.setdefault(number, target)
        return title, chapters


async def discover_manga(update, context, url):
    msg = await update.effective_message.reply_text(card('FETCHING MANGA', 'Discovering available chapters.'), parse_mode='HTML')
    try:
        title, chapters = await asyncio.wait_for(asyncio.to_thread(discover_sync, url), timeout=45)
    except Exception as exc:
        LOG.exception('Chapter discovery failed')
        await msg.edit_text(card('DISCOVERY FAILED', 'Could not read chapter links from this manga page. Check VPS logs.'), parse_mode='HTML')
        return
    if not chapters:
        await msg.edit_text(card('NO CHAPTERS FOUND', 'The site did not expose chapter links in the public HTML. This manga may require a site-specific adapter.'), parse_mode='HTML')
        return
    context.user_data['discovered_chapters'] = chapters
    context.user_data['discovered_title'] = title
    context.user_data['chapter_page'] = 0
    await show_chapter_page(context, update.effective_chat.id, 0, msg)


async def show_chapter_page(context, chat_id, page, message=None):
    chapters = context.user_data.get('discovered_chapters', {})
    title = context.user_data.get('discovered_title', 'Manga')
    ordered = sorted(chapters, key=lambda x: float(x))
    total_pages = max(1, (len(ordered)+24)//25)
    page = max(0, min(page, total_pages-1))
    subset = ordered[page*25:(page+1)*25]
    listing = ', '.join(subset)
    body = (f'<b>{smallcaps("MANGA DETECTED")}</b>\n\n'
            f'<b>{smallcaps("Title")}:</b> {html.escape(title)}\n'
            f'<b>{smallcaps("Available chapters")}:</b> {len(ordered)}\n'
            f'<b>{smallcaps("Chapter list")}:</b> {html.escape(listing)}\n'
            f'<b>{smallcaps("Page")}:</b> {page+1}/{total_pages}\n\n'
            f'<blockquote>{smallcaps("Select range and send 1-20 to process chapters sequentially.")}</blockquote>')
    rows = [[('Select Range','range_select'),('Close','close')]]
    navigation = []
    if page: navigation.append(('Previous',f'chapter_page:{page-1}'))
    if page+1<total_pages: navigation.append(('Next',f'chapter_page:{page+1}'))
    if navigation: rows.append(navigation)
    if message:
        await message.edit_text(body, parse_mode='HTML', reply_markup=keyboard(rows))
    else:
        await context.bot.send_message(chat_id, body, parse_mode='HTML', reply_markup=keyboard(rows))


async def show_range_prompt(context, chat_id, message):
    await message.edit_text(card('SELECT CHAPTER RANGE', 'Send a range such as 1-20. Chapters are processed and uploaded one by one.'), parse_mode='HTML', reply_markup=keyboard([[('Back','chapter_page:0'),('Close','close')]]))


def format_duration(seconds):
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours}h {minutes}m {secs}s'
    return f'{minutes}m {secs}s' if minutes else f'{secs}s'


def batch_progress(title, chapter, index, total):
    return (f'<b>{smallcaps("MULTIPLE CHAPTERS")}</b>\n\n'
            f'<b>{smallcaps("Manga")}:</b> {html.escape(str(title))}\n'
            f'<b>{smallcaps("Chapter")}:</b> {html.escape(str(chapter))}\n'
            f'<b>{smallcaps("Overall")}:</b> {index}/{total}')


async def run_chapter_batch(update, context, selected, missing, message_id=None):
    if BUSY.locked():
        await context.bot.send_message(update.effective_chat.id, smallcaps('Another job is running.'))
        return
    async with BUSY:
        context.application.bot_data['cancel_requested'] = False
        started = time.monotonic()
        title = context.user_data.get('discovered_title', 'Manga')
        # Reuse the chapter-range prompt message instead of sending another message.
        if message_id:
            try:
                msg = await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id, message_id=message_id,
                    text=batch_progress(title, selected[0][0], 1, len(selected)),
                    parse_mode='HTML', reply_markup=progress_keyboard())
            except Exception:
                LOG.exception('Could not reuse range prompt; creating fallback progress message')
                msg = await context.bot.send_message(update.effective_chat.id, batch_progress(title, selected[0][0], 1, len(selected)), parse_mode='HTML', reply_markup=progress_keyboard())
        else:
            msg = await context.bot.send_message(update.effective_chat.id, batch_progress(title, selected[0][0], 1, len(selected)), parse_mode='HTML', reply_markup=progress_keyboard())
        succeeded, failed = [], []
        total_pages, total_files, total_bytes = 0, 0, 0
        for index,(chapter,url) in enumerate(selected,1):
            if context.application.bot_data.get('cancel_requested'):
                break
            result = None
            reason = 'Download, PDF generation or upload failed'
            # Retry transient network and Telegram failures, but never restart
            # the whole batch. Exponential delay avoids hammering the source.
            for attempt in range(1, 4):
                if context.application.bot_data.get('cancel_requested'):
                    break
                try:
                    await msg.edit_text(batch_progress(title, chapter, index, len(selected)) +
                        f'\n<b>{smallcaps("Attempt")}:</b> {attempt}/3',
                        parse_mode='HTML', reply_markup=progress_keyboard())
                    result = await process_one(update, context, url, progress_message=msg, batch_mode=True)
                    if result:
                        break
                except Exception as exc:
                    reason = f'{type(exc).__name__}: {str(exc)[:130]}'
                    LOG.exception('Chapter %s attempt %s failed', chapter, attempt)
                if attempt < 3 and not context.application.bot_data.get('cancel_requested'):
                    await asyncio.sleep(min(2 ** attempt, 8))
            if result:
                succeeded.append(chapter)
                total_pages += result['pages']; total_files += result['files']; total_bytes += result['bytes']
            elif not context.application.bot_data.get('cancel_requested'):
                failed.append((chapter, url, reason))
            if not context.application.bot_data.get('cancel_requested'):
                await asyncio.sleep(1)
        cancelled = context.application.bot_data.get('cancel_requested', False)
        elapsed = format_duration(time.monotonic() - started)
        context.user_data['last_failed_chapters'] = [(chapter, url) for chapter, url, _ in failed]
        summary = (f'<b>{smallcaps("BATCH CANCELLED" if cancelled else "BATCH COMPLETED")}</b>\n\n'
                   f'<b>{smallcaps("Manga")}:</b> {html.escape(title)}\n\n'
                   f'<b>{smallcaps("Selected")}:</b> {len(selected)}\n'
                   f'<b>{smallcaps("Successful")}:</b> {len(succeeded)}  |  '
                   f'<b>{smallcaps("Failed")}:</b> {len(failed)}\n'
                   f'<b>{smallcaps("Missing from site")}:</b> {len(missing)}\n\n'
                   f'<b>{smallcaps("Total pages")}:</b> {total_pages}\n'
                   f'<b>{smallcaps("PDF files")}:</b> {total_files}\n'
                   f'<b>{smallcaps("Total size")}:</b> {total_bytes/1048576:.1f} MB\n'
                   f'<b>{smallcaps("Total time")}:</b> {elapsed}')
        if failed or missing:
            issues = [f'{smallcaps("Chapter")} {html.escape(str(ch))}: {html.escape(reason)}'
                      for ch, _, reason in failed]
            issues += [f'{smallcaps("Missing chapters")}: {html.escape(", ".join(map(str, missing)))}'] if missing else []
            issue_text = '\n'.join(issues)
            # Telegram editMessageText maximum is 4096 characters.
            summary += '\n\n<b>' + smallcaps('CHAPTER ISSUES') + '</b>\n' + issue_text[:max(0, 3900-len(summary))]
        retry_markup = keyboard([[('Retry Failed', 'retry_failed'), ('Close', 'close')]]) if failed else None
        try:
            await msg.edit_text(summary[:4096], parse_mode='HTML', reply_markup=retry_markup)
        except Exception:
            LOG.exception('Could not update final batch summary')
        context.application.bot_data['cancel_requested'] = False

# Publish the Telegram Menu button automatically on every bot startup.
# BotFather command setup is not required.
BOT_COMMANDS = [
    BotCommand('start', smallcaps('Open the welcome menu')),
    BotCommand('settings', smallcaps('Open bot settings (owner/admin)')),
    BotCommand('status', smallcaps('Check current task status')),
    BotCommand('cancel', smallcaps('Cancel the running task')),
    BotCommand('help', smallcaps('Show available commands')),
]

async def register_bot_commands(application):
    # Default commands appear in the Menu for all chats, including private chats.
    await application.bot.set_my_commands(BOT_COMMANDS)
    LOG.info('Registered %d Telegram menu commands automatically', len(BOT_COMMANDS))


def main():
    if not config.BOT_TOKEN or not config.OWNER_ID:
        raise RuntimeError('Set BOT_TOKEN and OWNER_ID in config.py')
    app = Application.builder().token(config.BOT_TOKEN).concurrent_updates(8).post_init(register_bot_commands).build()
    app.add_handler(CommandHandler(['start', 'help'], start))
    app.add_handler(CommandHandler('settings', settings))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.PHOTO, photo_input))
    app.add_handler(CommandHandler('status', status))
    app.add_handler(CommandHandler('cancel', cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    print('Sc Telegram bot starting (owner and admins)...', flush=True)
    app.run_polling(drop_pending_updates=False)


if __name__ == '__main__':
    main()
