# Arm CMSIS-Core headers (Apache-2.0).

load("@rules_cc//cc:defs.bzl", "cc_library")

package(default_visibility = ["//visibility:public"])

licenses(["notice"])

cc_library(
    name = "core",
    hdrs = glob(["CMSIS/Core/Include/*.h"]),
    includes = ["CMSIS/Core/Include"],
)
