// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
#include <iostream>
#include <stdexcept>
#include "../src/occlusion_evidence.hpp"
using lite3_perception::OcclusionEvidence;
void require(bool value, const char * label)
{
  if (!value) {throw std::runtime_error(label);}
  std::cout << "PASS " << label << '\n';
}
int main()
{
  OcclusionEvidence empty(.03);
  require(!empty.occluded(2, 0, .1, .06), "no invented occluder");
  OcclusionEvidence near(.03); near.add(1, 0, .05);
  require(near.occluded(2, 0, .1, .06), "near hit protects hidden old voxel");
  require(!near.occluded(.5, 0, .025, .06), "far hit does not hide nearer voxel");
  require(!near.occluded(2, 0, .8, .06), "different height is not whole-column occlusion");
  require(!near.occluded(2, 1, .1, .06), "unrelated direction stays clearable");
  OcclusionEvidence seam(.03); seam.add(-1, -.001, 0);
  require(seam.occluded(-2, .001, 0, .06), "azimuth wrap protects rear seam");
  OcclusionEvidence boundary(.03); boundary.add(1.5, 0, .01);
  require(boundary.occluded(1.475, .025, 0, .06), "cell-edge uncertainty retains surface");
  require(!boundary.occluded(1, .4, 0, .06), "shadow is angularly bounded");
  near.add(__builtin_nan(""), 0, 0);
  require(!near.occluded(2, 1, .1, .06), "invalid hit is ignored");
}
