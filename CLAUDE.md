# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

llm-cmd is an LLM plugin that generates and executes shell commands from natural language descriptions. It uses the LLM library's plugin system to register a `cmd` command that:

1. Takes a natural language prompt (e.g., "undo last git commit")
2. Uses an LLM to generate the corresponding shell command
3. Presents the command in an interactive editor using `prompt_toolkit`
4. Executes the command if the user confirms

**Warning**: This tool is potentially dangerous as it executes generated shell commands.

## Architecture

### Core Components

- **llm_cmd.py**: Single-file implementation containing:
  - `SYSTEM_PROMPT`: Instructs LLM to return raw command strings without markdown or delimiters
  - `register_commands()`: LLM plugin hook that registers the `cmd` command via `@llm.hookimpl`
  - `cmd()`: Main command handler that gets the LLM model, generates command, and passes to interactive executor
  - `interactive_exec()`: Uses `prompt_toolkit.PromptSession` with `BashLexer` syntax highlighting to present editable command before execution

### Environment Detection System

The system prompt is dynamically generated with contextual information to help the LLM generate appropriate commands:

- **detect_shell()**: Identifies shell (bash, zsh, PowerShell, cmd, etc.) using environment variables only
- **detect_os()**: Identifies OS and distro (Linux with distro name, macOS, Windows)
- **detect_environment()**: Detects hybrid environments (WSL, Git Bash, Cygwin)
- **detect_package_managers()**: Finds available package managers (apt, brew, pip, npm, etc.)
- **render_system_prompt()**: Combines all detection into a context-aware system prompt

This context helps the LLM generate commands appropriate for the user's specific environment.

### Plugin Registration

The project uses LLM's plugin system through entry points in pyproject.toml:
```toml
[project.entry-points.llm]
cmd = "llm_cmd"
```

This makes the command available as `llm cmd` when the package is installed.

### Interactive Command Editing

Uses `prompt_toolkit` for command editing with:
- Bash syntax highlighting via `PygmentsLexer(BashLexer)`
- Multiline support (Meta-Enter or Esc Enter to execute)
- `patch_stdout()` context manager for proper terminal handling

## Development Commands

### Setup
```bash
python3 -m venv venv
source venv/bin/activate
llm install -e '.[test]'
```

### Testing
```bash
pytest
```

### Manual Testing
After installing in editable mode, test with:
```bash
llm cmd list files in current directory
```

## Dependencies

- **llm**: Core LLM library and plugin system
- **prompt_toolkit>=3.0.43**: Interactive command editing
- **pygments>=2.17.2**: Syntax highlighting for bash commands

## Key Implementation Details

- Commands are executed with `subprocess.check_output(edited_command, shell=True)`
- Error handling prints exit status and stderr output
- Model selection: Uses `--model` flag or LLM's default model via `get_default_model()`
- API key handling: Supports `--key` flag or environment variables
- Custom system prompts: Supports `--system` flag to override default behavior
