import click
import llm
import string
import subprocess
from prompt_toolkit import PromptSession
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.patch_stdout import patch_stdout
from pygments.lexers.shell import BashLexer

from system_info import detect_shell, detect_os, detect_environment, detect_package_managers

SYSTEM_PROMPT = string.Template("""
Return only the command to be executed as a raw string, no string delimiters wrapping it, no yapping, no markdown, no fenced code blocks, what you return will be passed to subprocess.check_output() directly.

Environment: $shell_display on $os_display$env_suffix$pkg_suffix

If there is a lack of details, provide the most logical solution.
Ensure the output is a valid shell command for the environment.
If multiple steps are required, try to combine them using '&&' (For PowerShell, use ';' instead).

For example, if the user asks: undo last git commit
You return only: git reset --soft HEAD~1
""".strip())


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
        'env_suffix': f' [running in {environment.upper()}]' if environment != 'native' else '',
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
