"""firmware_image: turns a linked ELF into flashable images plus size and listing reports."""

load("@rules_cc//cc:find_cc_toolchain.bzl", "find_cc_toolchain", "use_cc_toolchain")

def _tool(cc_toolchain, name):
    # The toolchain only exposes objcopy/objdump paths; size sits next to them.
    return cc_toolchain.objcopy_executable.replace("objcopy", name)

def _firmware_image_impl(ctx):
    cc_toolchain = find_cc_toolchain(ctx)
    elf = ctx.file.elf
    stem = ctx.label.name
    tools = cc_toolchain.all_files

    out_elf = ctx.actions.declare_file(stem + ".elf")
    out_bin = ctx.actions.declare_file(stem + ".bin")
    out_hex = ctx.actions.declare_file(stem + ".hex")
    out_lst = ctx.actions.declare_file(stem + ".lst")
    out_size = ctx.actions.declare_file(stem + ".size.txt")

    ctx.actions.symlink(output = out_elf, target_file = elf)

    for fmt, out in [("binary", out_bin), ("ihex", out_hex)]:
        ctx.actions.run(
            executable = cc_toolchain.objcopy_executable,
            arguments = ["-O", fmt, elf.path, out.path],
            inputs = depset([elf], transitive = [tools]),
            outputs = [out],
            mnemonic = "Objcopy",
            progress_message = "Creating %{output}",
        )

    ctx.actions.run_shell(
        command = '"$1" -d -S -C "$2" > "$3"',
        arguments = [cc_toolchain.objdump_executable, elf.path, out_lst.path],
        inputs = depset([elf], transitive = [tools]),
        outputs = [out_lst],
        mnemonic = "Objdump",
        progress_message = "Disassembling %{label}",
    )

    ctx.actions.run_shell(
        command = '"$1" -A -x "$2" > "$3" && "$1" -B -d "$2" >> "$3"',
        arguments = [_tool(cc_toolchain, "size"), elf.path, out_size.path],
        inputs = depset([elf], transitive = [tools]),
        outputs = [out_size],
        mnemonic = "Size",
        progress_message = "Measuring %{label}",
    )

    files = [out_elf, out_bin, out_hex, out_lst, out_size]
    return [DefaultInfo(files = depset(files))]

firmware_image = rule(
    implementation = _firmware_image_impl,
    doc = "Produces <name>.elf/.bin/.hex plus a disassembly listing and a size report.",
    attrs = {
        "elf": attr.label(
            doc = "Linked firmware executable (a cc_binary).",
            allow_single_file = True,
            mandatory = True,
        ),
        "_cc_toolchain": attr.label(default = Label("@rules_cc//cc:current_cc_toolchain")),
    },
    toolchains = use_cc_toolchain(),
)
