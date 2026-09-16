# ST CMSIS device files for STM32H7 (Apache-2.0).

load("@rules_cc//cc:defs.bzl", "cc_library")

package(default_visibility = ["//visibility:public"])

licenses(["notice"])

cc_library(
    name = "headers",
    hdrs = glob(["Include/*.h"]),
    includes = ["Include"],
    deps = [
        "@@//bsp/nucleo_h743zi2:mcu_config",
        "@cmsis_core//:core",
    ],
)

# Reset handler, vector table and SystemInit. alwayslink keeps the vector
# table even though nothing references it by symbol.
cc_library(
    name = "startup_stm32h743",
    srcs = [
        "Source/Templates/gcc/startup_stm32h743xx.s",
        "Source/Templates/system_stm32h7xx.c",
    ],
    alwayslink = True,
    deps = [
        ":headers",
        "@stm32h7xx_hal_driver//:headers",
    ],
)
