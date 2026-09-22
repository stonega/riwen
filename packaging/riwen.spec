# Local prototype package. The project has not declared a redistribution license.
%global debug_package %{nil}
%global _python_bytecompile_extra 0
%global __provides_exclude_from ^%{_libdir}/riwen/.*$
%{!?riwen_version:%global riwen_version 0.1.0}
%{!?riwen_rime_include:%global riwen_rime_include %{_includedir}}
%global extension_uuid riwen-badge@riwen

Name:           riwen
Version:        %{riwen_version}
Release:        1%{?dist}
Summary:        Local candidate assistance and dictation for IBus Rime
License:        LicenseRef-riwen-unlicensed AND MIT
URL:            https://github.com/stonega/riwen
Source0:        %{name}-%{version}.tar.gz
ExclusiveArch:  x86_64
BuildRequires:  gcc-c++
BuildRequires:  librime-devel
BuildRequires:  glib2
BuildRequires:  python3
Requires:       python3 >= 3.12
Requires:       python3-gobject
Requires:       python3-pyyaml
Requires:       ibus
Requires:       ibus-rime
Requires:       librime-lua%{?_isa}
Requires:       lua-socket%{?_isa}
Requires:       curl
Requires:       uv
Requires:       pipewire-utils
Requires:       vulkan-loader%{?_isa}
Requires:       gnome-shell >= 51~
Requires:       gnome-shell < 52~

%description
Local Python inference bridge, isolated IBus Rime frontend, and GNOME Shell
extension. The native bridge is compiled at package build time. Bun is not a
runtime dependency. Models and the ASR environment are prepared per user.
Enable the extension explicitly after logging out and back in.

%prep
%autosetup

%build
mkdir -p app/native
g++ %{optflags} -std=c++17 -shared -fPIC -I%{riwen_rime_include} \
    app/src/native/rime_bridge.cpp -Wl,-l:librime.so.1 -ldl %{?build_ldflags} \
    -o app/native/libriwen-rime.so
glib-compile-schemas --strict extension/schemas

%install
mkdir -p %{buildroot}%{_libdir}/riwen %{buildroot}%{_bindir}
cp -a app/. %{buildroot}%{_libdir}/riwen/
python3 - <<'PY'
import json
from pathlib import Path
root = Path('%{buildroot}%{_libdir}/riwen')
(root / 'rpm-layout.json').write_text(json.dumps({'rime_plugin': '%{_libdir}/rime-plugins/librime-lua.so'}))
PY
cat > %{buildroot}%{_bindir}/riwen <<'SH'
#!/bin/sh
export PYTHONDONTWRITEBYTECODE=1
exec /usr/bin/python3 %{_libdir}/riwen/scripts/app.py "$@"
SH
chmod 0755 %{buildroot}%{_bindir}/riwen
mkdir -p %{buildroot}%{_datadir}/gnome-shell/extensions/%{extension_uuid}
cp -a extension/. %{buildroot}%{_datadir}/gnome-shell/extensions/%{extension_uuid}/
ln -s %{_libdir}/riwen %{buildroot}%{_datadir}/gnome-shell/extensions/%{extension_uuid}/app

%check
python3 - <<'PY'
import ast
from pathlib import Path
root = Path('%{buildroot}%{_libdir}/riwen')
for path in root.rglob('*.py'):
    ast.parse(path.read_text(), filename=str(path))
assert not list(root.rglob('*.ts'))
assert not (root / 'runtime/bun').exists()
PY

# No install/remove scriptlets: never touch a logged-in user's input method,
# enable extensions, start a root service, or remove per-user model/profile data.
%files
%{_bindir}/riwen
%{_libdir}/riwen/
%{_datadir}/gnome-shell/extensions/%{extension_uuid}/
