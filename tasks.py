"""Tasks file used by the *invoke* command.

This simplifies some common development tasks.

Run these tasks with the `invoke` tool.
"""

import getpass
from glob import glob
import json
import os
from pathlib import Path
import shutil
import sys
import tomllib

from invoke import Exit, run, task
import keyring
import semver
from setuptools_scm import get_version

PYTHONBIN = os.environ.get("PYTHONBIN", sys.executable)
# Put the path in quotes in case there is a space in it.
PYTHONBIN = f'"{PYTHONBIN}"'

with open("pyproject.toml", "rb") as fo:
    PKG_INFO = tomllib.load(fo)
PACKAGE_NAME = PKG_INFO["project"]["name"]
del fo

GPG = "gpg2"

CURRENT_USER = getpass.getuser()


@task
def info(ctx):
    """Show information about the current Python and environment."""
    version = get_version()
    suffix = get_suffix()
    print(f"Python being used: {PYTHONBIN}")
    print(f"Python extension suffix: {suffix}")
    print(f"Package version: {version}")
    venv = get_virtualenv()
    if venv:
        print("Virtual environment:", venv)


@task
def clean(ctx):
    """Clean out build and cache files. Remove extension modules."""
    ctx.run(r"find . -depth -type d -name __pycache__ -exec rm -rf {} \;")
    ctx.run('find devtest -name "*.so" -delete')
    with ctx.cd("docs"):
        ctx.run("rm -f modules/devtest.*.rst")
        ctx.run(f"{PYTHONBIN} -m sphinx.cmd.build -M clean . _build")


@task
def flake8(ctx, pathname="devtest"):
    """Run flake8 linter on the package."""
    ctx.run(f"{PYTHONBIN} -m flake8 {pathname}")


@task
def format(ctx, pathname="devtest", check=False):
    """Run yapf formatter on the specified file, or recurse into directory."""
    option = "-d" if check else "-i"
    recurse = "--recursive" if os.path.isdir(pathname) else ""
    ctx.run(f"{PYTHONBIN} -m yapf --style setup.cfg {option} {recurse} {pathname}")


@task
def format_changed(ctx, check=False, untracked=False):
    """Run yapf formatter on currently modified python files.

    If check option given then just show the diff.
    """
    option = "-d" if check else "-i"
    files = get_modified_files(untracked)
    if files:
        ctx.run(f'{PYTHONBIN} -m yapf --style setup.cfg {option} {" ".join(files)}')
    else:
        print("No changed python files.")


@task
def set_pypi_token(ctx):
    """Set the token in the local key ring."""
    pw = getpass.getpass("Enter pypi token? ")
    if pw:
        keyring.set_password(ctx.config.pypi.server, ctx.config.pypi.user, pw)
    else:
        raise Exit("No password entered.", 3)


@task
def cleandist(ctx):
    """Clean out distributably build subdirectory."""
    if os.path.isdir("dist"):
        shutil.rmtree("dist", ignore_errors=True)
        os.mkdir("dist")
    if os.path.isdir("wheelhouse"):
        shutil.rmtree("wheelhouse", ignore_errors=True)


@task
def freeze(ctx):
    """Freeze current package versions into requirements.txt file."""
    user = "" if os.environ.get("VIRTUAL_ENV") else "--user"
    pipcmd = (f"{PYTHONBIN} -m pip --disable-pip-version-check freeze"
              f" --exclude-editable --local {user} --requirement requirements-in.txt")
    freeze_output = ctx.run(pipcmd, hide="out")
    editablesout = ctx.run("pip list --editable --format json", hide="out")
    if ctx.config.run.dry:
        return
    with open("requirements.txt", "w") as fo:
        for line in freeze_output.stdout.splitlines():
            if "following requirements were added" in line:
                break
            fo.write(line + "\n")
        # Add back in dependencies installed as editable.
        editables = json.loads(editablesout.stdout)
        basereqs = [s.strip() for s in open("requirements-in.txt").readlines()]
        for editable in editables:
            for req in basereqs:
                if req.startswith(editable["name"]):
                    fo.write(f'{req}=={editable["version"]}\n')


@task(pre=[cleandist, freeze], aliases=["wheel"])
def build(ctx):
    """Build a standard wheel file, an installable format, with native arch."""
    ctx.run(f"{PYTHONBIN} -m build --no-isolation")


@task
def dev_requirements(ctx):
    """Install development requirements."""
    user = "" if os.environ.get("VIRTUAL_ENV") else "--user"
    ctx.run(
        f'{PYTHONBIN} -m pip install --index-url "{ctx.config.pypi.index}" '
        f"--upgrade {user} -r dev-requirements.txt",
        pty=True,
        hide=False,
    )


@task(pre=[dev_requirements])
def develop(ctx, uninstall=False):
    """Start developing in developer, or editable, mode."""
    user = "" if os.environ.get("VIRTUAL_ENV") else "--user"
    if uninstall:
        ctx.run(f"{PYTHONBIN} -m pip uninstall -y {PACKAGE_NAME}")
    else:
        ctx.run(f"{PYTHONBIN} -m pip --isolated install --index-url"
                f' "{ctx.config.pypi.index}" {user} --editable .')


@task(pre=[clean])
def update_deps(ctx):
    """Update the project dependencies to the most recent versions."""
    user = "" if os.environ.get("VIRTUAL_ENV") else "--user"
    deps = [s.strip() for s in open("requirements-in.txt").readlines()]
    if deps:
        deps = [f'"{s}"' for s in deps]
        ctx.run(f"{PYTHONBIN} -m pip install "
                f'--index-url "{ctx.config.pypi.index}" --upgrade'
                f' {user} {" ".join(deps)}')


@task
def test(ctx, testfile=None, ls=False):
    """Run unit tests. Use ls option to only list them."""
    if ls:
        ctx.run(f"{PYTHONBIN} -m pytest --collect-only -qq tests")
    elif testfile:
        ctx.run(f"{PYTHONBIN} -m pytest -s {testfile}", hide=False, pty=True)
    else:
        ctx.run(f"{PYTHONBIN} -m pytest tests", hide=False, pty=True)


@task
def tag(ctx, tag=None, major=False, minor=False, patch=False):
    """Tag or bump release with a semver tag.

    Makes a signed tag if you're a signer.
    """
    latest = None
    if tag is None:
        tags = get_tags()
        if not tags:
            latest = semver.VersionInfo(0, 0, 0)
        else:
            latest = tags[-1]
        if patch:
            nextver = latest.bump_patch()
        elif minor:
            nextver = latest.bump_minor()
        elif major:
            nextver = latest.bump_major()
        else:
            nextver = latest.bump_patch()
    else:
        if tag.startswith("v"):
            tag = tag[1:]
        try:
            nextver = semver.parse_version_info(tag)
        except ValueError:
            raise Exit("Invalid semver tag.", 2)

    print(latest, "->", nextver)
    tagopt = "-s" if CURRENT_USER in ctx.signers else "-a"
    ctx.run(f'git tag {tagopt} -m "Release v{nextver}" v{nextver}')


@task
def tag_delete(ctx, tag=None):
    """Delete a tag, both local and remote."""
    if tag:
        ctx.run(f"git tag -d {tag}")
        ctx.run(f"git push origin :refs/tags/{tag}")


@task(cleandist)
def sdist(ctx):
    """Build source distribution."""
    ctx.run(f"{PYTHONBIN} setup.py sdist")


@task
def build_ext(ctx):
    """Build compiled extension modules, in place."""
    ctx.run(f"{PYTHONBIN} setup.py build_ext --inplace")


@task(sdist)
def bdist(ctx):
    """Build a standard wheel file, an installable format."""
    ctx.run(f"{PYTHONBIN} setup.py bdist_wheel")


@task(bdist)
def sign(ctx):
    """Cryptographically sign dist with your default GPG key."""
    if CURRENT_USER in ctx.signers:
        ctx.run(f"{GPG} --detach-sign -a dist/devtest-*.whl")
        ctx.run(f"{GPG} --detach-sign -a dist/devtest-*.tar.gz")
    else:
        print("Not signing.")


@task(pre=[sign])
def publish(ctx):
    """Publish built wheel file to package repo."""
    token = get_pypi_token(ctx)
    distfiles = glob("dist/*.whl")
    distfiles.extend(glob("dist/*.tar.gz"))
    if not distfiles:
        raise Exit("Nothing in dist folder!")
    distfiles = " ".join(distfiles)
    ctx.run(f'{PYTHONBIN} -m twine upload --repository-url "{ctx.config.pypi.url}" '
            f"--username {ctx.config.pypi.user} --password {token} {distfiles}")


@task
def docs(ctx):
    """Build the HTML documentation."""
    ctx.run("rm docs/modules/devtest.*.rst", warn=True)
    ctx.run(f"{PYTHONBIN} -m sphinx.ext.apidoc --force --separate --no-toc"
            " --output-dir docs/modules devtest")
    with ctx.cd("docs"):
        ctx.run(f"{PYTHONBIN} -m sphinx.cmd.build -M html . _build")
    if os.environ.get("DISPLAY"):
        ctx.run("xdg-open docs/_build/html/index.html")


@task
def branch(ctx, name=None):
    """start a new branch, both local and remote tracking."""
    if name:
        ctx.run(f"git checkout -b {name}")
        ctx.run(f"git push -u origin {name}")
    else:
        ctx.run("git --no-pager branch")


@task
def branch_delete(ctx, name=None):
    """Delete local, remote and tracking branch by name."""
    if name:
        ctx.run(f"git branch -d {name}", warn=True)  # delete local branch
        ctx.run(f"git branch -d -r {name}", warn=True)  # delete local tracking info
        ctx.run(f"git push origin --delete {name}", warn=True)  # delete remote (origin) branch.
    else:
        print("Supply a branch name: --name <name>")


@task(pre=[sdist])
def docker_build(ctx):
    """Build docker image."""
    version = get_version()
    if not version:
        raise Exit("Need to tag a version first.", 2)
    environ = {
        "PYVER": "{}.{}".format(sys.version_info.major, sys.version_info.minor),
        "VERSION": version,
        "PYPI_HOST": ctx.config.pypi.server,
        "PYPI_REPO": ctx.config.pypi.index,
    }
    ctx.run(
        "docker build --build-arg PYVER --build-arg VERSION --build-arg"
        f" PYPI_REPO --build-arg {ctx.config.pypi.server} -t devtest:{version} .",
        env=environ,
    )
    print(f"Done. To run it:\n docker run -it devtest:{version}")


# Helper functions follow.
def get_virtualenv():
    venv = os.environ.get("VIRTUAL_ENV")
    if venv and os.path.isdir(venv):
        return venv
    return None


def get_tags():
    rv = run('git tag -l "v*"', hide="out")
    vilist = []
    for line in rv.stdout.split():
        try:
            vi = semver.parse_version_info(line[1:])
        except ValueError:
            pass
        else:
            vilist.append(vi)
    vilist.sort()
    return vilist


def get_pypi_token(ctx):
    cred = keyring.get_credential(ctx.config.pypi.server, ctx.config.pypi.user)
    if not cred:
        raise Exit("You must set the pypi token with the set-pypi-token target.", 1)
    return cred.password


def get_suffix():
    return run(
        f"{PYTHONBIN} -c 'import sysconfig;"
        ' print(sysconfig.get_config_vars()["EXT_SUFFIX"])\'',
        hide=True,
    ).stdout.strip()  # noqa


def resolve_path(base, p):
    p = Path(p)
    return str(base / p)


def find_git_base():
    """Find the base directory of this git repo.

    The git status output is always relative to this directory.
    """
    start = Path.cwd().resolve()
    while start:
        if (start / ".git").exists():
            return start
        start = start.parent
    raise Exit("Not able to find git repo base.")


def get_modified_files(untracked):
    """Find the list of modified and, optionally, untracked Python files.

    If `untracked` is True, also include untracked Python files.
    """
    filelist = []
    gitbase = find_git_base()
    gitout = run("git status --porcelain=1 -z", hide=True)
    for line in gitout.stdout.split("\0"):
        if line:
            if not line.endswith(".py"):
                continue
            if line[0:2] == " M":
                filelist.append(resolve_path(gitbase, line[3:]))
            if untracked and line[0:2] == "??":
                filelist.append(resolve_path(gitbase, line[3:]))
    return filelist
