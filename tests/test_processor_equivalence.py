"""SYNTHETIC processor/library comparisons; no weights, network or medical images.

These check our native crop against independent transformers/timm processing
implementations using declared synthetic configurations. They do not authenticate
publisher files or establish equivalence on the real medical release.
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from cancer_workbench.adapters import encoder
from helpers import write_processor_config

HAS_PROCESSORS = all(importlib.util.find_spec(n) for n in ("torch", "torchvision", "timm", "transformers", "PIL"))


@unittest.skipUnless(HAS_PROCESSORS, "needs the ml extra for independent synthetic processor comparisons")
class SyntheticProcessorEquivalenceTests(unittest.TestCase):
    def setUp(self):
        import torch
        from PIL import Image, ImageDraw
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.paths = []
        # Odd crop margins, both orientations, square, upsampling and a large JPEG.
        for i, (w,h,ext) in enumerate(((700,500,"png"),(500,701,"png"),(517,1333,"png"),
                                      (288,288,"png"),(31,17,"png"),(1600,1100,"jpg"))):
            im=Image.linear_gradient("L").resize((w,h))
            draw=ImageDraw.Draw(im)
            draw.rectangle((w//5,h//7,w*3//5,h*4//5),fill=219)
            draw.ellipse((w//2,h//4,w*4//5,h*3//4),fill=23)
            path=self.root/f"SYNTHETIC-{i}.{ext}"; im.save(path);self.paths.append(path)
        self.torch = torch

    def compare(self, enc, process, tolerance):
        from PIL import Image
        spec=encoder.ENCODERS[enc]
        mean=self.torch.tensor(spec["mean"]).view(3,1,1)
        std=self.torch.tensor(spec["std"]).view(3,1,1)
        for path in self.paths:
            with self.subTest(encoder=enc,source=path.name), Image.open(path) as image:
                ours=(encoder.load_image(path,spec["size"],"native_crop",spec["crop_offset"])-mean)/std
                reference=process(image.convert("RGB"))
                self.assertEqual(tuple(ours.shape),tuple(reference.shape))
                self.assertLessEqual(float((ours-reference).abs().max()),tolerance)

    def test_rad_dino_native_crop_matches_transformers_pil_synthetic_config(self):
        from transformers import BitImageProcessorPil
        enc="rad-dino";write_processor_config(self.root,enc)
        config=json.loads((self.root/encoder.ENCODERS[enc]["processor_config"]).read_text())
        processor=BitImageProcessorPil(**config)
        self.compare(enc,lambda image:processor(images=image,return_tensors="pt")["pixel_values"][0],
                     1.01/255/encoder.ENCODERS[enc]["std"][0])

    def test_rad_dino_torchvision_quantization_is_bounded_on_synthetic_fixtures(self):
        from transformers import BitImageProcessor
        enc="rad-dino";write_processor_config(self.root,enc)
        config=json.loads((self.root/encoder.ENCODERS[enc]["processor_config"]).read_text())
        processor=BitImageProcessor(**config)
        # The default transformers backend uses tensor/Torchvision bicubic;
        # our pipeline uses PIL. Two gray levels are observed on a sharp edge
        # in this finite fixture set. This is not exact or universal equivalence.
        self.compare(enc,lambda image:processor(images=image,return_tensors="pt")["pixel_values"][0],
                     2.01/255/encoder.ENCODERS[enc]["std"][0])

    def test_resnet_native_crop_matches_timm_synthetic_config(self):
        import timm
        enc="resnet50-a1-in1k";write_processor_config(self.root,enc)
        cfg=json.loads((self.root/encoder.ENCODERS[enc]["processor_config"]).read_text())["pretrained_cfg"]
        transform=timm.data.create_transform(**timm.data.resolve_data_config({},pretrained_cfg=cfg,use_test_size=True))
        self.compare(enc,transform,1e-6)


if __name__ == "__main__":
    unittest.main()
