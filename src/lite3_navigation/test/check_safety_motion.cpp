// Copyright 2026 STAR-626
// SPDX-License-Identifier: BSD-3-Clause
// Numerical model regression only: not Gazebo/RL safety certification.
#include "../src/safety_motion.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace lite3_navigation::safety;
int main()
{
  Settings cfg;
  int checks = 0;
  auto require = [&](bool condition, const char * name) {
      if (!condition) {throw std::runtime_error(name);}
      ++checks; std::cout << "PASS " << name << '\n';
    };
  const Pose origin{0., 0., 0.};
  auto wall = [](const Pose & p) {return p.x < .20;};
  require(stoppingClear(origin, {0., 0., 0.}, cfg, wall), "stationary body does not invent momentum");
  require(!stoppingClear(origin, {.4, 0., 0.}, cfg, wall), "measured forward motion cannot stop before 20cm wall");
  require(!commandClear(origin, {.4, 0., 0.}, {0., 0., 0.}, cfg, wall), "zero requested command cannot erase measured momentum");
  double final_x = 0.;
  require(stoppingClear(origin, {.4, 0., 0.}, cfg,
    [&](const Pose & p) {final_x = p.x; return true;}), "open stopping path accepted");
  require(std::abs(final_x - .26) < .001, "reaction plus braking displacement matches 26cm analytical result");
  require(!stoppingClear({0., 0., std::acos(-1.)/2}, {.4, 0., 0.}, cfg,
    [](const Pose & p) {return p.y < .20;}), "body velocity converted to world heading");
  require(!stoppingClear(origin, {-.3, 0., 0.}, cfg,
    [](const Pose & p) {return p.x > -.10;}), "backward stopping checked too");
  require(!stoppingClear(origin, {0., .3, 0.}, cfg,
    [](const Pose & p) {return p.y < .10;}), "lateral stopping checked too");
  const auto turning_body = [](const Pose & p) {
      const double dx = .30 - p.x, dy = .25 - p.y;
      const double x = std::cos(p.yaw)*dx + std::sin(p.yaw)*dy;
      const double y = -std::sin(p.yaw)*dx + std::cos(p.yaw)*dy;
      return std::abs(x) > .42 || std::abs(y) > .20;
    };
  require(turning_body(origin), "obstacle outside current rectangular body");
  require(!stoppingClear(origin, {0., 0., .6}, cfg, turning_body), "rotating body corner sweeps into obstacle despite stationary centre");
  require(!commandClear(origin, {0., 0., 0.}, {.4, 0., 0.}, cfg,
    [](const Pose & p) {return p.x < .35;}), "instantaneous fast response checked as well as delayed response");
  const double nan = std::numeric_limits<double>::quiet_NaN();
  require(!stoppingClear(origin, {nan, 0., 0.}, cfg, wall), "invalid measured velocity rejected");
  require(!commandClear(origin, {0., 0., 0.}, {0., nan, 0.}, cfg, wall), "invalid requested velocity rejected");
  require(commandClear(origin, {0., 0., 0.}, {.32, .1, .6}, cfg,
    [](const Pose &) {return true;}), "open combined translation and turn accepted");
  std::cout << checks << " numerical checks passed; no Gazebo or RL motion tested\n";
}
