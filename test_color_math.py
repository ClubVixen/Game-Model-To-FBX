import unittest
import numpy as np
from hair_bake import linear, srgb, sample

class ColorMathTests(unittest.TestCase):
    def test_linear_roundtrip(self):
        a=np.linspace(0,1,1000)
        np.testing.assert_allclose(srgb(linear(a)),a,atol=1e-6)
    def test_linear_tint(self):
        np.testing.assert_allclose(srgb(linear(np.array([.5]))*.5),[.36078],atol=1e-4)
    def test_uv_centers_and_repeat(self):
        image=np.array([[[1.,0,0],[0,1,0]],[[0,0,1],[1,1,1]]])
        uv=np.array([[.25,.25],[.75,.75],[1.25,.25]])
        np.testing.assert_allclose(sample(image,uv),[[1,0,0],[1,1,1],[1,0,0]])
    def test_bilinear_center(self):
        image=np.array([[[1.,0,0],[0,1,0]],[[0,0,1],[1,1,1]]])
        np.testing.assert_allclose(sample(image,np.array([[.5,.5]])),[[.5,.5,.5]])

if __name__=='__main__':unittest.main()
