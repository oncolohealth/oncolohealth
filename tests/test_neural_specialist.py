import tempfile
import unittest
import importlib.util
from pathlib import Path
from unittest import mock

from cancer_workbench.research import neural

@unittest.skipUnless(all(importlib.util.find_spec(p) is not None for p in ['torch','numpy','PIL']), 'optional neural research dependencies not installed')
class NeuralSpecialistTests(unittest.TestCase):
    def test_rgb_transform_preserves_color_instead_of_collapsing_to_grayscale(self):
        import numpy as np
        array=np.zeros((28,28,3),dtype=np.uint8);array[:,:,0]=255
        tensor=neural.tensor_for(array,"RGB")
        self.assertEqual(tuple(tensor.shape),(3,288,288))
        self.assertAlmostEqual(float(tensor[0,100,100]),(1-.485)/.229,places=5)
        self.assertAlmostEqual(float(tensor[1,100,100]),(0-.456)/.224,places=5)

    def test_ultrasound_gray_replication_uses_each_channel_normalization_once(self):
        import numpy as np
        tensor=neural.tensor_for(np.full((28,28),128,dtype=np.uint8),"L")
        spec=neural.preprocessing("L")
        for c in range(3):self.assertAlmostEqual(float(tensor[c,100,100]),(128/255-spec['mean'][c])/spec['std'][c],places=5)

    def test_source_upload_and_array_transform_match_exactly(self):
        import numpy as np
        import torch
        from PIL import Image
        array=np.arange(2352,dtype=np.uint8).reshape(28,28,3)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"neutral.png";Image.fromarray(array).save(path)
            self.assertTrue(torch.equal(neural.tensor_for(array,"RGB"),neural.tensor_for(neural.source_array(path,"RGB"),"RGB")))

    def test_shape_or_pixel_scale_mismatch_is_rejected(self):
        import numpy as np
        for a in [np.zeros((28,28,3),dtype=np.float32),np.zeros((32,32,3),dtype=np.uint8)]:
            with self.assertRaises(ValueError):neural.tensor_for(a,"RGB")

    def test_changed_weight_is_rejected_before_model_load(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'model.safetensors').write_bytes(b'changed');(root/'config.json').write_text('{}')
            with mock.patch.object(neural,'MODEL_ROOT',root):
                with self.assertRaisesRegex(ValueError,'identity changed'):neural.identity('RGB')

if __name__=='__main__':unittest.main()
