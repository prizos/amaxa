"""cc_toolchain_config for the Arm GNU Toolchain (arm-none-eabi-gcc), bare-metal Cortex-M7.

Instantiated from arm_gnu_toolchain.BUILD, i.e. inside the downloaded toolchain
repository, so every path below is relative to that repository's root.
"""

load("@rules_cc//cc:action_names.bzl", "ACTION_NAMES")
load(
    "@rules_cc//cc:cc_toolchain_config_lib.bzl",
    "feature",
    "flag_group",
    "flag_set",
    "tool_path",
)
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/toolchains:cc_toolchain_config_info.bzl", "CcToolchainConfigInfo")

_ALL_C_COMPILE_ACTIONS = [
    ACTION_NAMES.c_compile,
    ACTION_NAMES.cpp_compile,
]

_ALL_ASSEMBLE_ACTIONS = [
    ACTION_NAMES.assemble,
    ACTION_NAMES.preprocess_assemble,
]

_ALL_LINK_ACTIONS = [
    ACTION_NAMES.cpp_link_executable,
]

def _flags(actions, flags):
    return flag_set(actions = actions, flag_groups = [flag_group(flags = flags)])

def _impl(ctx):
    root = ctx.label.workspace_root  # e.g. external/+_repo_rules+arm_gnu_toolchain_linux_aarch64
    gcc_dir = "{}/lib/gcc/arm-none-eabi/{}".format(root, ctx.attr.gcc_version)

    tool_paths = [
        tool_path(name = name, path = "bin/arm-none-eabi-" + tool)
        for name, tool in [
            ("ar", "ar"),
            ("cpp", "cpp"),
            ("dwp", "gcc"),  # not used for bare-metal builds
            ("gcc", "gcc"),
            ("gcov", "gcov"),
            ("ld", "ld"),
            ("nm", "nm"),
            ("objcopy", "objcopy"),
            ("objdump", "objdump"),
            ("strip", "strip"),
        ]
    ]

    # CPU and ABI flags must match on every compile, assemble and link action,
    # otherwise the linker picks the wrong multilib (newlib, libgcc).
    cpu_flags = ["-mcpu=" + ctx.attr.cpu] + ctx.attr.fpu_flags + ["-mthumb"]

    features = [
        feature(
            name = "cpu_flags",
            enabled = True,
            flag_sets = [
                _flags(_ALL_C_COMPILE_ACTIONS + _ALL_ASSEMBLE_ACTIONS + _ALL_LINK_ACTIONS, cpu_flags),
            ],
        ),
        feature(
            name = "default_compile_flags",
            enabled = True,
            flag_sets = [
                _flags(_ALL_C_COMPILE_ACTIONS + _ALL_ASSEMBLE_ACTIONS, [
                    # Keep paths relative so Bazel's header checks and sandboxing work.
                    "-no-canonical-prefixes",
                    "-fno-canonical-system-headers",
                    # Reproducible output.
                    "-Wno-builtin-macro-redefined",
                    "-D__DATE__=\"redacted\"",
                    "-D__TIMESTAMP__=\"redacted\"",
                    "-D__TIME__=\"redacted\"",
                ]),
                _flags(_ALL_C_COMPILE_ACTIONS, [
                    "-ffunction-sections",
                    "-fdata-sections",
                    "-fno-common",
                    "-Wall",
                ]),
                _flags([ACTION_NAMES.c_compile], ["-std=gnu17"]),
            ],
        ),
        feature(
            name = "dbg",
            flag_sets = [_flags(_ALL_C_COMPILE_ACTIONS, ["-Og", "-g3"])],
        ),
        feature(
            name = "fastbuild",
            flag_sets = [_flags(_ALL_C_COMPILE_ACTIONS, ["-O1", "-g"])],
        ),
        feature(
            name = "opt",
            flag_sets = [_flags(_ALL_C_COMPILE_ACTIONS, ["-O2", "-g"])],
        ),
        feature(
            name = "default_link_flags",
            enabled = True,
            flag_sets = [
                _flags(_ALL_LINK_ACTIONS, [
                    "-no-canonical-prefixes",
                    "--specs=nano.specs",
                    "-Wl,--gc-sections",
                    "-Wl,--no-warn-rwx-segments",
                ]),
            ],
        ),
        feature(name = "supports_dynamic_linker", enabled = False),
        feature(name = "supports_pic", enabled = False),
    ]

    return cc_common.create_cc_toolchain_config_info(
        ctx = ctx,
        toolchain_identifier = "arm-none-eabi-gcc-" + ctx.attr.gcc_version,
        compiler = "gcc",
        target_cpu = "armv7e-mf",
        target_libc = "newlib",
        abi_version = "eabi",
        abi_libc_version = "newlib",
        host_system_name = "local",
        target_system_name = "arm-none-eabi",
        tool_paths = tool_paths,
        features = features,
        cxx_builtin_include_directories = [
            gcc_dir + "/include",
            gcc_dir + "/include-fixed",
            root + "/arm-none-eabi/include",
        ],
    )

arm_none_eabi_toolchain_config = rule(
    implementation = _impl,
    attrs = {
        "cpu": attr.string(default = "cortex-m7"),
        "fpu_flags": attr.string_list(default = ["-mfpu=fpv5-d16", "-mfloat-abi=hard"]),
        "gcc_version": attr.string(mandatory = True),
    },
    provides = [CcToolchainConfigInfo],
)
