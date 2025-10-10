import click
import llm
import os
import platform
import shutil
import string
import subprocess
from prompt_toolkit import PromptSession
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.patch_stdout import patch_stdout
from pygments.lexers.shell import BashLexer

SYSTEM_PROMPT = string.Template("""
Return only the command to be executed as a raw string, no string delimiters wrapping it, no yapping, no markdown, no fenced code blocks, what you return will be passed to subprocess.check_output() directly.

Environment: $shell_display on $os_display$env_suffix$pkg_suffix

If there is a lack of details, provide the most logical solution.
If multiple steps are required, try to combine them using '&&' (For PowerShell, use ';' instead).

For example, if the user asks: undo last git commit
You return only: git reset --soft HEAD~1
""".strip())


def detect_shell():
    """Detect current shell cross-platform (using env vars only)"""
    system = platform.system()

    # Check for PowerShell first (cross-platform)
    if os.getenv("PSModulePath"):
        if system == "Windows":
            # On Windows, distinguish PowerShell 5.1 vs 7+
            # PSModulePath contains "WindowsPowerShell" in PS5, but just "PowerShell" in PS7
            ps_module_path = os.getenv("PSModulePath", "")
            if "WindowsPowerShell" in ps_module_path:
                return "powershell", "5"  # Windows PowerShell 5.1

            # Secondary check: PS7 adds "PowerShell\7" to PATH
            path = os.getenv("Path", "")
            if "PowerShell\\7" in path or "PowerShell/7" in path:
                return "pwsh", "7"

            # Tertiary fallback: check which executable is available
            if shutil.which("pwsh"):
                return "pwsh", "7"

            # If PSModulePath exists but no WindowsPowerShell, assume PS7
            return "pwsh", "7"
        else:
            # On Linux/macOS, PowerShell is always pwsh 7+
            # (PowerShell 5.1 is Windows-only)
            return "pwsh", "7"

    # Windows-specific shells
    if system == "Windows":
        # Check for Git Bash/MSYS/Cygwin on Windows
        shell = os.getenv("SHELL")
        if shell:
            shell_name = os.path.basename(shell)
            return shell_name, ""

        # Fall back to cmd.exe
        return "cmd", ""

    # Unix-like systems: $SHELL is reliable
    shell_name = os.path.basename(os.getenv("SHELL") or "sh")
    return shell_name, ""


def detect_os():
    """Detect OS - simplified version info"""
    os_type = platform.system()

    if os_type == "Linux":
        # Just get distro name, skip version/kernel details
        try:
            with open('/etc/os-release') as f:
                for line in f:
                    if line.startswith('NAME='):
                        distro = line.split('=')[1].strip().strip('"')
                        return f"Linux ({distro})"
        except:
            pass
        return "Linux"

    elif os_type == "Darwin":
        # Just "macOS" - version rarely matters for commands
        return "macOS"

    elif os_type == "Windows":
        # Simple: just Windows (no build numbers)
        return "Windows"

    else:
        return os_type


def detect_environment():
    """Detect hybrid environments (WSL, Git Bash, etc.)"""
    os_name = platform.system()

    # WSL detection
    if os_name == "Linux":
        if os.getenv("WSL_DISTRO_NAME"):
            return "wsl"
        try:
            with open('/proc/version', 'r') as f:
                if 'microsoft' in f.read().lower():
                    return "wsl"
        except:
            pass

    # Git Bash / MSYS
    if os.getenv("MSYSTEM"):
        return "gitbash"

    # Cygwin
    if os.getenv("CYGWIN"):
        return "cygwin"

    return "native"


def detect_package_managers():
    """Detect available package managers"""
    managers = []

    # Check common package managers
    for pm in ['apt', 'dnf', 'yum', 'pacman', 'zypper', 'apk',  # Linux
                'snap', 'flatpak',  # Universal Linux
                'brew', 'port',  # macOS
                'choco', 'scoop', 'winget',  # Windows
                'nix', 'guix',  # Alternative
                'pipx', 'uv', 'pip', 'npm', 'cargo', 'gem']:  # Language
        if shutil.which(pm):
            managers.append(pm)

    return managers


def render_system_prompt():
    """Build system prompt with minimal context"""
    shell_name, shell_version = detect_shell()
    os_display = detect_os()
    environment = detect_environment()
    package_managers = detect_package_managers()

    # Format shell display (only show version when it matters)
    if shell_version:
        shell_display = f"{shell_name} {shell_version}"
    else:
        shell_display = shell_name

    # Format template variables
    context = {
        'shell_display': shell_display,
        'os_display': os_display,
        'env_suffix': f'[running in {environment.upper()}]' if environment != 'native' else '',
        'pkg_suffix': f'\nPackage managers: {", ".join(package_managers)}' if package_managers else '',
    }

    return SYSTEM_PROMPT.safe_substitute(context)


@llm.hookimpl
def register_commands(cli):
    @cli.command()
    @click.argument("args", nargs=-1)
    @click.option("-m", "--model", default=None, help="Specify the model to use")
    @click.option("-s", "--system", help="Custom system prompt")
    @click.option("--key", help="API key to use")
    def cmd(args, model, system, key):
        """Generate and execute commands in your shell"""
        from llm.cli import get_default_model
        prompt = " ".join(args)
        model_id = model or get_default_model()
        model_obj = llm.get_model(model_id)
        if model_obj.needs_key:
            model_obj.key = llm.get_key(key, model_obj.needs_key, model_obj.key_env_var)
        result = model_obj.prompt(prompt, system=system or render_system_prompt())
        interactive_exec(str(result))


def interactive_exec(command):
    session = PromptSession(lexer=PygmentsLexer(BashLexer))
    with patch_stdout():
        if '\n' in command:
            print("Multiline command - Meta-Enter or Esc Enter to execute")
            edited_command = session.prompt("> ", default=command, multiline=True)
        else:
            edited_command = session.prompt("> ", default=command)
    try:
        output = subprocess.check_output(
            edited_command, shell=True, stderr=subprocess.STDOUT
        )
        print(output.decode())
    except subprocess.CalledProcessError as e:
        print(f"Command failed with error (exit status {e.returncode}): {e.output.decode()}")
