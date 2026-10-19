# Third-party notices

Lite3 robot model resources originate from DeepRobotics / DeepRoboticsLab.

- Upstream: https://github.com/DeepRoboticsLab/deep_robotics_model
- Local upstream revision: `75824b516ecc8fa3f8f7ce5d6577e1e86d6b614f`
- Copyright (c) 2024, DeepRoboticsLab
- License: BSD 3-Clause; the complete unmodified local upstream license is preserved in `src/lite3_description/LICENSE.DeepRoboticsLab.txt`.
- Local origin checkout: `/home/ma/deep_robotics_model`; that checkout is not included in this project.

## Included resources

The four files in `src/lite3_description/meshes/` (`hip.STL`, `shank.STL`, `thigh.STL`, `torso.STL`) match upstream `Lite3/urdf/meshes/` byte for byte (SHA-256 verified).

`src/lite3_description/urdf/Lite3_original.urdf` matches upstream `Lite3/urdf/Lite3.urdf` byte for byte. `Lite3.urdf` is the project's adapted copy, using ROS package mesh paths. `Lite3_gazebo.urdf` adds the project's Gazebo control plugin. All copies retain the model's existing exporter comments.

## Redistribution conditions

Retain the upstream copyright notice, license conditions and disclaimer. For binary distribution, reproduce them in documentation or other accompanying materials. Do not use the copyright holder's or contributors' names to endorse derived products without prior written permission.

This notice does not assign a license to independently authored project files. The original description/gazebo package.xml license declarations remain TODO; select the project's own license separately before offering broad reuse permissions. The new lite3_control package has its own BSD-3-Clause LICENSE.

## Pretrained policy and deployment adaptations

- Upstream: https://github.com/DeepRoboticsLab/Lite3_rl_deploy
- Exact revision: `1c4a8f14c9c531903fa5a26783e3f9b99d1039d9`.
- Copyright (c) 2025, DeepRoboticsLab; BSD 3-Clause. The unmodified license is preserved at `external/lite3_rl_deploy/LICENSE.DeepRoboticsLab.txt`.
- Included: the original `policy/ppo/policy.onnx`, six locally modified/new source snapshots and a replayable patch. See that directory's README and UPSTREAM.json for paths and SHA-256.
- Local modifications: space-to-stop keyboard input, initialization of the previous ONNX action, policy initialization before starting its thread, and the opt-in local UDP velocity adapter with input synchronization and stop handling.
- The local upstream tree was checked for license notices; no separate policy-weight license notice was found. Preserve the upstream root license with the policy and keep this repository private. Recheck any supplemental weight terms before a future public release.
- Do not imply upstream endorsement. Unmodified dependency repositories, bundled libraries, virtual environments and generated logs are not copied into this project.

Lite3 pretrained policy and deployment source originate from DeepRobotics / DeepRoboticsLab.

## Warehouse world and matching map

- Source recorded during import: https://github.com/PalashMendhe/robotics-amr-ws
- Fixed import revision: `c64bd49f2764b9d80941b51cff61b761d0112f87`.
- Included resources: `src/lite3_gazebo/worlds/large_warehouse.sdf` and matching `maps/large_warehouse.pgm` / `.yaml`.
- MIT License, Copyright (c) 2026 Palash Siddharth Mendhe; the imported license text is preserved unchanged as `src/lite3_gazebo/worlds/LICENSE.large_warehouse.txt`.
- Retain the copyright and permission notice with these resources. The source project's other robots, arm code, dependencies and entire repository are not copied.

## Gazebo GUI configuration and target picker

`src/lite3_gazebo/config/target_picker.config` derives from the installed Gazebo
Sim 8 default `gui/gui.config` (source: https://github.com/gazebosim/gz-sim/tree/gz-sim8/src/gui).
The local changes add the Lite3 picker and adjust window dimensions. The upstream
Apache-2.0 license is included as `config/LICENSE.gui-config.Apache-2.0.txt`.
The new independently authored `gui/Lite3TargetPicker.*`, `gui/target_picker.qrc`
and picker tests use BSD-3-Clause; their text is in `gui/LICENSE` and is installed
with the plugin. This does not change the licensing of older package files.

## Project development archive

`docs/development_history` contains this project's available visible conversation text and selected test evidence, exported at the owner's request. No screenshots, other conversations, internal reasoning or raw tool credentials are included. Historical text is a development record, not the current operation manual or a blanket license for third-party resources.

## Smac Lattice runtime dependency (2026-10-17)

Navigation uses the installed ROS2 Jazzy `nav2_smac_planner` plugin and its packaged
5cm/0.5m/omni motion primitives by default (diff for the RPP fallback). Launch resolves the installed package share directory;
no copy of that upstream repository or primitive asset is embedded here. Upstream:
https://github.com/ros-navigation/navigation2/tree/jazzy/nav2_smac_planner .
See the installed package's LICENSE when redistributing its binaries/assets.
