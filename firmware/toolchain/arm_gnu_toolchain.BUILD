# BUILD file overlaid on the downloaded Arm GNU Toolchain archive.
# Only the files needed for Cortex-M7 hard-float (thumb/v7e-m+dp/hard) C builds
# are exposed, which keeps the per-action sandbox small.

load("@@//toolchain:cc_toolchain_config.bzl", "arm_none_eabi_toolchain_config")
load("@rules_cc//cc:defs.bzl", "cc_toolchain")

package(default_visibility = ["//visibility:public"])

GCC_VERSION = "15.2.1"

MULTILIB = "thumb/v7e-m+dp/hard"

filegroup(
    name = "compiler_files",
    srcs = glob([
        "bin/arm-none-eabi-cpp",
        "bin/arm-none-eabi-gcc",
        "arm-none-eabi/bin/as",
        "arm-none-eabi/include/**",
        "lib/gcc/arm-none-eabi/{}/include/**".format(GCC_VERSION),
        "lib/gcc/arm-none-eabi/{}/include-fixed/**".format(GCC_VERSION),
        "libexec/gcc/arm-none-eabi/{}/**".format(GCC_VERSION),
    ]),
)

filegroup(
    name = "linker_files",
    srcs = glob([
        "bin/arm-none-eabi-gcc",
        "arm-none-eabi/bin/ld",
        "arm-none-eabi/bin/ld.bfd",
        "arm-none-eabi/lib/*.specs",
        "arm-none-eabi/lib/{}/**".format(MULTILIB),
        "lib/gcc/arm-none-eabi/{}/{}/**".format(GCC_VERSION, MULTILIB),
        "libexec/gcc/arm-none-eabi/{}/**".format(GCC_VERSION),
    ]),
)

filegroup(
    name = "ar_files",
    srcs = glob([
        "bin/arm-none-eabi-ar",
        "arm-none-eabi/bin/ar",
    ]),
)

filegroup(
    name = "binutils_files",
    srcs = glob([
        "bin/arm-none-eabi-nm",
        "bin/arm-none-eabi-objcopy",
        "bin/arm-none-eabi-objdump",
        "bin/arm-none-eabi-size",
        "bin/arm-none-eabi-strip",
    ]),
)

filegroup(
    name = "all_files",
    srcs = [
        ":ar_files",
        ":binutils_files",
        ":compiler_files",
        ":linker_files",
    ],
)

filegroup(name = "empty")

arm_none_eabi_toolchain_config(
    name = "cc_toolchain_config",
    gcc_version = GCC_VERSION,
)

cc_toolchain(
    name = "cc_toolchain",
    all_files = ":all_files",
    ar_files = ":ar_files",
    as_files = ":compiler_files",
    compiler_files = ":compiler_files",
    dwp_files = ":empty",
    linker_files = ":linker_files",
    objcopy_files = ":binutils_files",
    strip_files = ":binutils_files",
    supports_param_files = True,
    toolchain_config = ":cc_toolchain_config",
)
