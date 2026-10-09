"""Offline cover proxy tests with fake image HTTP responses."""
import io
import sys
import tempfile
import unittest
import types
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:import pymongo
except ImportError:
    fake=types.ModuleType('pymongo');fake.MongoClient=object
    sys.modules['pymongo']=fake

from PIL import Image
import cover_proxy

class Response:
    status_code=200
    is_redirect=False
    headers={'Content-Type':'image/png','Cache-Control':'public, max-age=3600'}
    def __init__(self,data):self.data=data
    def raise_for_status(self):pass
    def close(self):pass
    def iter_content(self,chunk_size):yield self.data

class Client:
    def __init__(self,response):self.resp=response;self.calls=0
    def get(self,*args,**kwargs):self.calls+=1;return self.resp

class CoverProxyTests(unittest.TestCase):
    def test_safe_download_and_disk_cache(self):
        output=io.BytesIO();Image.new('RGB',(120,180),'red').save(output,'PNG')
        client=Client(Response(output.getvalue()))
        with tempfile.TemporaryDirectory() as tmp,patch.object(cover_proxy,'CACHE_DIR',Path(tmp)):
            url='https://s4.anilist.co/file/anilistcdn/media/manga/cover/test.png'
            data=cover_proxy.cover_bytes(url,session=client)
            self.assertEqual(Image.open(io.BytesIO(data)).size,(120,180))
            self.assertEqual(cover_proxy.cover_bytes(url,session=client),data)
            self.assertEqual(client.calls,1)

    def test_reject_unapproved_host(self):
        with self.assertRaises(ValueError):
            cover_proxy.cover_bytes('http://127.0.0.1/admin',session=Client(None))

    def test_no_store_respected(self):
        output=io.BytesIO();Image.new('RGB',(10,14),'blue').save(output,'PNG')
        response=Response(output.getvalue())
        response.headers={'Content-Type':'image/png','Cache-Control':'no-store'}
        with tempfile.TemporaryDirectory() as tmp,patch.object(cover_proxy,'CACHE_DIR',Path(tmp)):
            cover_proxy.cover_bytes('https://s4.anilist.co/a.png',session=Client(response))
            self.assertFalse(list(Path(tmp).iterdir()))

if __name__=='__main__':unittest.main()
