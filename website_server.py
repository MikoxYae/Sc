"""Website and public MongoDB-backed catalog API on port 1980."""
import json, logging, os, threading, sys, urllib.parse, ssl, requests
from datetime import date, datetime
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from functools import partial
from http.cookies import SimpleCookie
from pymongo.errors import PyMongoError,DuplicateKeyError
from catalog_db import public_catalog,CATEGORIES,collection,public_title,PUBLIC_TITLE_PROJECTION
import web_auth
import chapter_reader
import cover_proxy
LOG=logging.getLogger('Sc.website');ROOT=Path(__file__).resolve().parent/'website'

def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError('Unsupported JSON value: '+type(value).__name__)

class Handler(SimpleHTTPRequestHandler):
    def list_directory(self,path):self.send_error(403);return None
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
        self.send_header('Cache-Control','no-store' if self.path.startswith('/api/') else 'public, max-age=120')
        super().end_headers()
    def log_message(self,fmt,*args):LOG.info('Website: '+fmt,*args)
    def respond(self,code,obj,extra=None):
        raw=json.dumps(obj,ensure_ascii=False,default=_json_default).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)))
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(raw)
    def token(self):
        try:return SimpleCookie(self.headers.get('Cookie','')).get('sc_session').value
        except (AttributeError,ValueError):return ''
    def do_GET(self):
        u=urllib.parse.urlsplit(self.path)
        if u.path=='/api/health':
            return self.respond(200,{'ok':True,'service':'sc-website'})
        if u.path=='/api/cover':
            q=urllib.parse.parse_qs(u.query)
            cat=q.get('category',[''])[0];slug=q.get('slug',[''])[0]
            if cat not in CATEGORIES or not __import__('re').fullmatch(r'[a-z0-9][a-z0-9-]{0,130}',slug):
                return self.respond(400,{'error':'Invalid cover identifier'})
            try:
                col=collection(cat)
                if col is None:return self.respond(503,{'error':'Catalog unavailable'})
                doc=col.find_one({'slug':slug,'published':True,'chapters.0':{'$exists':True}},
                                 {'_id':0,'cover_url':1})
                if not doc or not cover_proxy.valid_cover(doc.get('cover_url')):
                    return self.respond(404,{'error':'No verified cover available'})
                picture=cover_proxy.cover_bytes(doc['cover_url'])
                self.send_response(200)
                self.send_header('Content-Type','image/webp')
                self.send_header('Content-Length',str(len(picture)))
                self.send_header('Cache-Control','public, max-age=3600')
                self.end_headers()
                self.wfile.write(picture)
                return
            except (ValueError, requests.RequestException, OSError):
                return self.respond(502,{'error':'Provider cover currently unavailable'})
            except (PyMongoError,RuntimeError):
                return self.respond(503,{'error':'Catalog temporarily unavailable'})
        if u.path=='/api/catalog':
            q=urllib.parse.parse_qs(u.query)
            category=q.get('category',[''])[0] or None
            if category and category not in CATEGORIES:return self.respond(400,{'error':'Invalid category'})
            try:page=max(1,min(1000,int(q.get('page',['1'])[0])))
            except ValueError:page=1
            try:return self.respond(200,public_catalog(category,q.get('q',[''])[0],page))
            except (PyMongoError,RuntimeError) as exc:
                LOG.warning('Catalog unavailable: %s',type(exc).__name__)
                return self.respond(503,{'error':'Catalog database unavailable'})
        if u.path=='/api/title':
            q=urllib.parse.parse_qs(u.query);cat=q.get('category',[''])[0];slug=q.get('slug',[''])[0]
            if cat not in CATEGORIES or not slug or len(slug)>160:return self.respond(400,{'error':'Invalid title'})
            try:
                col=collection(cat)
                if col is None:return self.respond(503,{'error':'Catalog database unavailable'})
                doc=col.find_one({'slug':slug,'published':True,'chapters.0':{'$exists':True}},PUBLIC_TITLE_PROJECTION)
                if not doc:return self.respond(404,{'error':'Title not found'})
                return self.respond(200,public_title(doc,cat))
            except (PyMongoError,RuntimeError) as exc:
                LOG.warning('Title lookup unavailable (%s)',type(exc).__name__)
                return self.respond(503,{'error':'Catalog database unavailable'})
        if u.path in ('/api/chapter', '/api/chapter/page'):
            q=urllib.parse.parse_qs(u.query)
            cat=q.get('category',[''])[0];slug=q.get('slug',[''])[0];num=q.get('chapter',[''])[0]
            try:
                chapter_reader.validate(cat,slug,num)
                # Adult reading stays restricted until age verification is implemented.
                if cat.startswith('adult_'):
                    return self.respond(403,{'error':'Adult reader requires age verification; not enabled yet'})
                if u.path=='/api/chapter':
                    return self.respond(200,chapter_reader.prepare(cat,slug,num))
                page=q.get('page',[''])[0]
                chapter_reader.chapter_record(cat,slug,num)
                path=chapter_reader.page_path(cat,slug,num,page)
                data=path.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type','image/webp')
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','private, max-age=3600')
                self.end_headers()
                self.wfile.write(data)
                return
            except ValueError as exc:return self.respond(400,{'error':str(exc)})
            except FileNotFoundError:return self.respond(404,{'error':'Chapter or page not available'})
            except (PyMongoError,RuntimeError, OSError) as exc:
                LOG.warning('Reader unavailable: %s',type(exc).__name__)
                return self.respond(503,{'error':'Chapter storage is temporarily unavailable. Please retry.'},
                                    {'Retry-After':'3'})
            except Exception as exc:
                # Always return JSON instead of unexpectedly closing the TCP connection.
                LOG.error('Unexpected chapter endpoint failure (%s)',type(exc).__name__)
                return self.respond(500,{'error':'Chapter could not be loaded. Please retry.'})
        if u.path=='/api/me':
            try:return self.respond(200,{'user':web_auth.identity(self.token())})
            except (PyMongoError,RuntimeError):return self.respond(200,{'user':None})
        if u.path.startswith('/api/'):return self.respond(404,{'error':'Not found'})
        return super().do_GET()
    def proxy_https(self):
        # Only trust proxy headers from a local reverse proxy on loopback.
        return (os.getenv('SC_TRUST_LOCAL_PROXY') == '1'
                and self.client_address[0] in ('127.0.0.1', '::1')
                and self.headers.get('X-Forwarded-Proto', '').lower() == 'https')
    def do_POST(self):
        if self.path not in ('/api/register','/api/login','/api/logout'):return self.respond(404,{'error':'Not found'})
        if not isinstance(self.connection, ssl.SSLSocket) and not self.proxy_https():
            return self.respond(403,{'error':'Sign in requires HTTPS. Configure SC_TLS_CERT and SC_TLS_KEY.'})
        # Cross-origin writes blocked; deployment must use HTTPS reverse proxy.
        origin=self.headers.get('Origin','');host=self.headers.get('Host','')
        if origin and urllib.parse.urlsplit(origin).netloc!=host:return self.respond(403,{'error':'Invalid origin'})
        try:
            length=int(self.headers.get('Content-Length','0') or '0')
        except (ValueError,TypeError):
            return self.respond(400,{'error':'Invalid request length'})
        if length<0 or length>4096:return self.respond(413,{'error':'Request too large'})
        try:
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict):raise ValueError('Invalid request data')
            if self.path=='/api/logout':
                web_auth.logout(self.token());return self.respond(200,{'ok':True},{'Set-Cookie':'sc_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0'})
            email=payload.get('email','');password=payload.get('password','')
            if not isinstance(email,str) or not isinstance(password,str):raise ValueError('Invalid input')
            if self.path=='/api/register':
                web_auth.register(email,password);return self.respond(201,{'ok':True})
            token=web_auth.login(email,password)
            secure='; Secure' if isinstance(self.connection, ssl.SSLSocket) or self.proxy_https() else ''
            return self.respond(200,{'ok':True},{'Set-Cookie':'sc_session='+token+'; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800'+secure})
        except (json.JSONDecodeError,UnicodeDecodeError):return self.respond(400,{'error':'Invalid JSON request'})
        except DuplicateKeyError:return self.respond(409,{'error':'Account already exists'})
        except ValueError as exc:return self.respond(400,{'error':str(exc)[:120]})
        except (PyMongoError,RuntimeError) as exc:
            LOG.warning('Authentication backend unavailable: %s',type(exc).__name__)
            return self.respond(503,{'error':'Database unavailable'})
class QuietHTTPServer(ThreadingHTTPServer):
    daemon_threads=True;allow_reuse_address=True;request_queue_size=128
    def handle_error(self,request,client_address):
        if isinstance(sys.exc_info()[1],(ConnectionResetError,BrokenPipeError,ConnectionAbortedError)):return
        super().handle_error(request,client_address)
class RedirectToHTTPS(BaseHTTPRequestHandler):
    """Never accept credentials over plain HTTP; redirect to TLS listener."""
    def _redirect(self):
        from urllib.parse import quote
        hostname = os.getenv('SC_PUBLIC_HOST', '159.195.245.129')
        tls_port = int(os.getenv('SC_HTTPS_PORT', '1981'))
        path = self.path if self.path.startswith('/') and not self.path.startswith('//') else '/'
        location = f'https://{hostname}:{tls_port}{path}'
        self.send_response(308 if self.command == 'GET' else 307)
        self.send_header('Location', location)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', '0')
        self.end_headers()
    def do_GET(self): self._redirect()
    def do_HEAD(self): self._redirect()
    def do_POST(self): self._redirect()
    def log_message(self, fmt, *args): LOG.debug('HTTP redirect: '+fmt, *args)


def start_website(port=None,host=None):
    port=int(port or os.getenv('SC_WEB_PORT', '1276'))
    host=host or os.getenv('SC_WEB_HOST','0.0.0.0')
    cert=os.getenv('SC_TLS_CERT'); key=os.getenv('SC_TLS_KEY')
    if bool(cert) != bool(key):
        raise RuntimeError('Both SC_TLS_CERT and SC_TLS_KEY must be configured')
    if os.getenv('SC_TRUST_LOCAL_PROXY') == '1' and (cert or key):
        raise RuntimeError('Do not combine local reverse proxy mode with direct TLS')
    if cert and key:
        tls_port=int(os.getenv('SC_HTTPS_PORT','1981'))
        if tls_port == port: raise RuntimeError('HTTPS and redirect ports must differ')
        server=QuietHTTPServer((host,tls_port),partial(Handler,directory=str(ROOT)))
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certfile=cert,keyfile=key)
        server.socket=context.wrap_socket(server.socket,server_side=True)
        try:
            redirect=QuietHTTPServer((host,port),RedirectToHTTPS)
        except Exception:
            server.server_close()
            raise
        threading.Thread(target=redirect.serve_forever,name='ScHttpRedirect',daemon=True).start()
        LOG.info('HTTP %s redirects to HTTPS %s',port,tls_port)
    else:
        try:
            server=QuietHTTPServer((host,port),partial(Handler,directory=str(ROOT)))
        except OSError as exc:
            if exc.errno == 98:
                raise RuntimeError(f'Website port {port} is already occupied. Stop the other Sc instance or use systemctl restart sc-miko.service.') from exc
            raise
        LOG.warning('Website is running without TLS; account endpoints reject remote logins')
    threading.Thread(target=server.serve_forever,name='ScWebsite',daemon=True).start()
    LOG.info('Sc website started on %s://%s:%s','https' if cert and key else 'http',host,tls_port if cert and key else port)
    return server
