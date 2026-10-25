"""A disconnected progress sink must stop its owned CT worker and save the failure."""
import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest import mock
from cancer_workbench.research import runtime as rt,ct

class CTStreamCancellationTests(unittest.TestCase):
 def test_progress_disconnect_terminates_only_owned_worker_and_records_failure(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);raw=b'synthetic CT boundary fixture';sha=hashlib.sha256(raw).hexdigest()
   model={'id':'fixture','state':'verified','classes':['nodule'],'backend':'ct','formats':['nifti'],'training':{},'preprocessing':{},'implementation_sha256':'fixture','limitations':[]}
   events=[]
   class Worker:
    pid=12345;returncode=None
    def __init__(self,*args,**kwargs):events.append('started')
    def wait(self,timeout):
     if self.returncode is None:raise subprocess.TimeoutExpired('owned fixture',timeout)
     events.append('waited');return self.returncode
    def poll(self):return self.returncode
    def kill(self):events.append('killed');self.returncode=1
   worker=Worker()
   def taskkill(args,**kwargs):
    self.assertEqual(args,['taskkill','/PID','12345','/T','/F']);worker.kill();return mock.Mock(returncode=0)
   def progress(event):
    self.assertEqual(event['phase'],'local_CT_inference');events.append('disconnected');raise BrokenPipeError('client closed')
   with mock.patch.object(rt,'INPUTS',root/'inputs'),mock.patch.object(rt,'RESULTS',root/'results'),mock.patch.object(rt,'REFERENCES',root/'refs'), \
        mock.patch.object(rt,'profile',return_value=(root,model)),mock.patch.object(ct,'validate'), \
        mock.patch('subprocess.Popen',return_value=worker),mock.patch('subprocess.run',side_effect=taskkill):
    rt.INPUTS.mkdir();p=rt.INPUTS/(sha+'.nii.gz');p.write_bytes(raw)
    rt._save(rt.INPUTS/(sha+'.json'),{'id':sha,'file':p.name,'sha256':sha,'format':'nifti'})
    rt._save(root/'manifest.json',model)
    result=rt.predict('fixture',sha,on_progress=progress)
    self.assertEqual(result['status'],'failed');self.assertIn('client closed',result['error'])
    self.assertTrue((rt.RESULTS/(result['id']+'.json')).is_file())
    self.assertEqual(events,['started','disconnected','killed','waited'])

if __name__=='__main__':unittest.main()
