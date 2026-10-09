import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import types
try:
 import pymongo
except ImportError:
 stub=types.ModuleType('pymongo');stub.MongoClient=object;sys.modules['pymongo']=stub
from metadata_engine import MetadataEngine,normalize
class TestMetadata(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize('Ｓｏｌｏ   Leveling'),'solo leveling')
    def test_search_rejects_short(self):
        with self.assertRaises(ValueError):MetadataEngine().search('x')
    def test_anilist_mapping(self):
        class Fake(MetadataEngine):
            def request(self,*args,**kwargs):
                return {'data':{'Page':{'media':[{'id':1,'title':{'english':'Solo Leveling'},'staff':{},'coverImage':{},'status':'FINISHED','countryOfOrigin':'KR','startDate':{},'endDate':{}}]}}}
        r=Fake().anilist('Solo Leveling')[0]
        self.assertEqual(r['type'],'Manhwa')
        self.assertEqual(r['status'],'Completed')
        self.assertIsNone(r['chapters'])
if __name__=='__main__':unittest.main()
