# ST STM32H7 HAL driver (BSD-3-Clause).

load("@rules_cc//cc:defs.bzl", "cc_library")

package(default_visibility = ["//visibility:public"])

licenses(["notice"])

cc_library(
    name = "headers",
    hdrs = glob(["Inc/**/*.h"]),
    includes = [
        "Inc",
        "Inc/Legacy",
    ],
    deps = [
        "@@//bsp:hal_conf",
        "@cmsis_device_h7//:headers",
    ],
)

# Every HAL module is compiled; modules disabled in stm32h7xx_hal_conf.h
# compile to nothing and unused functions are dropped by --gc-sections.
cc_library(
    name = "hal",
    srcs = glob(
        ["Src/stm32h7xx_hal*.c"],
        exclude = ["Src/*_template.c"],
    ),
    deps = [":headers"],
)
