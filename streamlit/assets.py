# -*- coding: utf-8 -*-
"""The aircraft symbol, as a PNG data URI.

Baked in rather than fetched: deck.gl's IconLayer needs an image, and a page
that carries its own has no host to reach and nothing to fail. White on
transparent, so `mask: True` lets the layer tint each aircraft by state.
Shape is a plan-view airliner, nose up (north) before rotation.
"""

PLANE_PNG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAAACEklEQVR42u3dy07EMBAFUdzq///lZsOCDeIxjMb2PbUmmSRVbgcEYs3MG3Ipj0AAEAAEkMsIAAIIX/0jAAgAAvDyJwBBCAACsNoFAAGYDAKAAKxyAQhEABCA1S0ACMCkEACpAoAAIICbx/8IAAKAACAACAACgAAgAAgAAoAAIAAIAAKAACAACAACgAAgAAgAAoAAIAAIANvSl9/f/NPxywTIk/+sc5kAB4m/fho08dkhFPnZ20ITnz0NmvjsEIr87G2hic+eBkX+U695BBDwEE+Otz207G2hyM+eaOXhZEfeHkb2tlDkZ0++Jj57IlRS7d4PXhsA8RsulCY+e1uoGyq2LewXAPGHLKgmPntbKPKzt4UmPnsaNPHZIdTl8teDe+Wjx2+/LfSF4teTzzk3TYO+RPx60WfN6SH0wfLXZtcwG4ew/hLAkH5NDF9OgxN+LfzEv7o55p2hSc+OoUnPjqFJ3+beJyWAZOnbTYcmPTuGJj07hiY9O4YmPTuGJj07hiY9O4YmPTuGIj8yhh8FgAAEIAAIAAKAACAACAACgAAggGuYFx0rgMPlfz7HCOA88bNhTAI4ZNXHRFDkZ0dQ5Ge/F/i/geHToMjPjqAOFz8izAxgBJkbwLg+EwACgADwMB187+vG7+sF8Dvh333NCOB+6T89fgSQIT0qhib8Xz5zBHC/9CunQ5Efd31+DgAB4IN3UVmKAVOPM5MAAAAASUVORK5CYII="
)
PLANE_SIZE = 128
