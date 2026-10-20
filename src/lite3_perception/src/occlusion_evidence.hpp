// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
#pragma once
#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace lite3_perception
{
// Conservative spherical depth envelope of real non-ground hits. It guards
// existing voxel evidence; it never fills an object's unseen shape or creates
// an obstacle. Positions are relative to the same scan's true sensor origin.
class OcclusionEvidence
{
public:
  explicit OcclusionEvidence(double beam_margin)
  : beam_margin_(beam_margin), depth_(azimuth_bins * elevation_bins,
      std::numeric_limits<double>::infinity()) {}

  void add(double x, double y, double z)
  {
    const double range = std::sqrt(x*x + y*y + z*z);
    if (!std::isfinite(range) || range < 1e-6) {return;}
    const auto a = azimuth(std::atan2(y, x));
    const auto e = elevation(std::atan2(z, std::hypot(x, y)));
    auto & value = depth_[e*azimuth_bins + a];
    value = std::min(value, range);
  }

  bool occluded(double x, double y, double z, double voxel_radius) const
  {
    const double rho = std::hypot(x, y), range = std::hypot(rho, z);
    if (!std::isfinite(range) || range <= voxel_radius) {return true;}
    const double angle = std::atan2(z, rho);
    // Voxel angular extent plus finite scan spacing. Using a depth minimum is
    // deliberately conservative near grazing edges, rather than treating a
    // neighbouring free beam as proof that the entire old voxel is empty.
    const double half_e = std::asin(std::min(1.0, voxel_radius/range)) + beam_margin_;
    const double half_a = std::min(pi,
      std::asin(std::min(1.0, voxel_radius/std::max(rho, 1e-9))) +
      beam_margin_/std::max(std::cos(angle), .01));
    const int a = azimuth(std::atan2(y, x));
    const int radius_a = std::min(azimuth_bins/2,
      static_cast<int>(std::ceil(half_a/step)) + 1);
    const int min_e = elevation(angle-half_e), max_e = elevation(angle+half_e);
    for (int e = min_e; e <= max_e; ++e) {
      for (int da = -radius_a; da <= radius_a; ++da) {
        const int aa = (a + da + azimuth_bins) % azimuth_bins;
        if (depth_[e*azimuth_bins + aa] <= range + voxel_radius) {return true;}
      }
    }
    return false;
  }

private:
  static constexpr double pi = 3.14159265358979323846;
  static constexpr double step = pi/180.0;
  static constexpr int azimuth_bins = 360, elevation_bins = 180;
  static int azimuth(double angle)
  {
    return std::clamp(static_cast<int>((angle+pi)/step), 0, azimuth_bins-1);
  }
  static int elevation(double angle)
  {
    return std::clamp(static_cast<int>((angle+pi/2)/step), 0, elevation_bins-1);
  }
  double beam_margin_;
  std::vector<double> depth_;
};
}  // namespace lite3_perception
