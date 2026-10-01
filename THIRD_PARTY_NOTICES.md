# Third-party notices

Lite3 robot model resources originate from DeepRobotics / DeepRoboticsLab.

- Upstream: https://github.com/DeepRoboticsLab/deep_robotics_model
- Local upstream revision: `75824b516ecc8fa3f8f7ce5d6577e1e86d6b614f`
- Copyright (c) 2024, DeepRoboticsLab
- License: BSD 3-Clause; the complete unmodified local upstream license is preserved in `src/lite3_description/LICENSE.DeepRoboticsLab.txt`.
- Local origin checkout: `~/deep_robotics_model`; that checkout is not included in this project.

## Included resources

The four files in `src/lite3_description/meshes/` (`hip.STL`, `shank.STL`, `thigh.STL`, `torso.STL`) match upstream `Lite3/urdf/meshes/` byte for byte (SHA-256 verified).

`src/lite3_description/urdf/Lite3_original.urdf` matches upstream `Lite3/urdf/Lite3.urdf` byte for byte. `Lite3.urdf` is the project's adapted copy, using ROS package mesh paths; both copies retain their existing exporter comments and are preserved without modification during this synchronization.

## Redistribution conditions

Retain the upstream copyright notice, license conditions and disclaimer. For binary distribution, reproduce them in documentation or other accompanying materials. Do not use the copyright holder's or contributors' names to endorse derived products without prior written permission.

This notice does not assign a license to independently authored project files. The two package.xml license declarations remain TODO; select the project's own license separately before offering broad reuse permissions.
