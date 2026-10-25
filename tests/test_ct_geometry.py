"""Synthetic DICOM geometry fixtures; no medical performance is tested."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

from cancer_workbench.research import ct

@unittest.skipUnless(all(importlib.util.find_spec(p) is not None for p in ['numpy','nibabel','pydicom']), 'optional imaging dependencies not installed')
class CTGeometryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.series=self.root/'series';self.series.mkdir()

    def make_series(self,spacing=1.25,thickness=None,gap=False,mixed=False):
        import numpy as np
        from pydicom.dataset import FileDataset,FileMetaDataset
        from pydicom.uid import CTImageStorage,ExplicitVRLittleEndian,generate_uid
        uid=generate_uid()
        for k in range(16):
            meta=FileMetaDataset();meta.MediaStorageSOPClassUID=CTImageStorage
            meta.MediaStorageSOPInstanceUID=generate_uid();meta.TransferSyntaxUID=ExplicitVRLittleEndian
            p=self.series/(f'{15-k:03}.dcm')
            d=FileDataset(str(p),{},file_meta=meta,preamble=b'\0'*128)
            d.SOPClassUID=meta.MediaStorageSOPClassUID;d.SOPInstanceUID=meta.MediaStorageSOPInstanceUID
            d.SeriesInstanceUID=generate_uid() if mixed and k==15 else uid
            d.Modality='CT';d.Rows=16;d.Columns=16;d.PixelSpacing=[.5,.75]
            d.ImageOrientationPatient=[1,0,0,0,1,0]
            d.ImagePositionPatient=[10,20,(k+(1 if gap and k>=8 else 0))*spacing]
            d.SliceThickness=thickness or spacing;d.RescaleSlope=1;d.RescaleIntercept=-1000;d.RescaleType='HU'
            d.PhotometricInterpretation='MONOCHROME2';d.SamplesPerPixel=1
            d.BitsAllocated=16;d.BitsStored=16;d.HighBit=15;d.PixelRepresentation=1
            d.PixelData=(np.arange(256,dtype=np.int16).reshape(16,16)+k).tobytes()
            d.save_as(p,enforce_file_format=True)

    def test_position_sort_hu_and_lps_to_ras_geometry(self):
        import numpy as np,nibabel as nib
        self.make_series()
        p=self.root/'CT.nii.gz';receipt=ct.prepare_dicom_series(self.series,p,self.root/'source.json')
        image=nib.load(p);array=np.asanyarray(image.dataobj)
        self.assertEqual(array.shape,(16,16,16));self.assertEqual(float(array[0,0,0]),-1000.)
        self.assertEqual(float(array[0,0,15]),-985.)
        self.assertTrue(np.allclose(image.affine,[[0,-.75,0,-10],[-.5,0,0,-20],[0,0,1.25,0],[0,0,0,1]]))
        self.assertFalse(receipt['reference_used']);self.assertEqual(ct.validate(p)['shape'],[16,16,16])

    def test_thick_slices_do_not_become_eligible_by_resampling(self):
        self.make_series(spacing=3.)
        with self.assertRaisesRegex(ValueError,'at most2.5mm'):
            ct.prepare_dicom_series(self.series,self.root/'out.nii.gz',self.root/'out.json')

    def test_irregular_slice_gap_is_rejected(self):
        self.make_series(gap=True)
        with self.assertRaisesRegex(ValueError,'regularly spaced'):
            ct.prepare_dicom_series(self.series,self.root/'out.nii.gz',self.root/'out.json')

    def test_mixed_series_is_rejected(self):
        self.make_series(mixed=True)
        with self.assertRaisesRegex(ValueError,'exactly one CT series'):
            ct.prepare_dicom_series(self.series,self.root/'out.nii.gz',self.root/'out.json')

    def test_undeclared_volume_is_not_assumed_to_be_hu_ct(self):
        import nibabel as nib,numpy as np
        p=self.root/'unknown.nii.gz';nib.save(nib.Nifti1Image(np.zeros((28,28,28),dtype=np.uint8),np.eye(4)),p)
        with self.assertRaisesRegex(ValueError,'explicitly prepared HU'):
            ct.validate(p)

    def test_missing_or_nonfinite_calibration_is_rejected(self):
        import pydicom
        self.make_series()
        p=next(self.series.glob('*.dcm'));d=pydicom.dcmread(p)
        del d.RescaleIntercept;d.save_as(p,enforce_file_format=True)
        with self.assertRaisesRegex(ValueError,'explicit HU calibration'):
            ct.prepare_dicom_series(self.series,self.root/'missing.nii.gz',self.root/'missing.json')
        d.RescaleIntercept=float('nan');d.save_as(p,enforce_file_format=True)
        with self.assertRaisesRegex(ValueError,'calibration must be finite'):
            ct.prepare_dicom_series(self.series,self.root/'nan.nii.gz',self.root/'nan.json')

    def test_nonpositive_spacing_and_nonfinite_voxels_are_rejected(self):
        import pydicom,nibabel as nib,numpy as np
        self.make_series()
        p=next(self.series.glob('*.dcm'));d=pydicom.dcmread(p);d.PixelSpacing=[0,.75];d.save_as(p,enforce_file_format=True)
        with self.assertRaisesRegex(ValueError,'strictly positive spacing|Changing orientation or pixel spacing'):
            ct.prepare_dicom_series(self.series,self.root/'bad.nii.gz',self.root/'bad.json')
        data=np.zeros((16,16,16),dtype=np.float32);data[0,0,0]=np.nan
        image=nib.Nifti1Image(data,np.eye(4));image.header['descrip']=ct.MARKER;image.header.set_xyzt_units('mm')
        target=self.root/'nan.nii.gz';nib.save(image,target)
        with self.assertRaisesRegex(ValueError,'voxels must be finite'):
            ct.validate(target)

if __name__=='__main__':unittest.main()
