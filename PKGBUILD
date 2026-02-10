# Maintainer: Ice Year
_appname=feishin
pkgname=iipython-feishin-electron-bin
_pkgname=feishin
pkgver=26.01.22_1.0_3
_tag=26.01.22-1.0-3
_upstream_tag=26.01.22-1.0
_assetver=26.01.22
_assetname=Feishin-linux-amd64.deb
_electronversion=39
pkgrel=1
pkgdesc="A modern self-hosted music player (iiPythonx build, prebuilt, system-wide electron, lite rolldown-vite build)"
arch=('x86_64')
url="https://github.com/iceyear/iipython-feishin-electron-bin"
license=('GPL-3.0-only')
provides=("${_appname}=${pkgver}")
conflicts=(
    "${_appname}"
    "${_appname}-bin"
    "${_appname}-electron-bin"
)
depends=(
    "electron${_electronversion}"
)
optdepends=(
    'mpv: Alternative audio backend'
)
makedepends=(
    'asar'
    'nodejs'
    'npm'
)
source=("${pkgname%-bin}.sh")
source_x86_64=(
    "${pkgname%-bin}-${pkgver}-x86_64.deb::${url}/releases/download/${_tag}/${_assetname}"
)
sha256sums=('4497d4c2cfb24ca0665cbeabf377a6bc850a8cfd6dd17469b0dc937a9ed6bf65')
sha256sums_x86_64=('39acafbefebc222569c682045b6c1d86e319335f775a3cc2d5e1352ebafc0ce9')

_get_electron_version() {
    _elec_ver="$(strings "${srcdir}/opt/Feishin/feishin" | grep '^Chrome/[0-9.]* Electron/[0-9]' | cut -d'/' -f3 | cut -d'.' -f1)"
    echo -e "The electron version is: \033[1;31m${_elec_ver}\033[0m"
}

prepare() {
    sed -i -e "
        s/@electronversion@/${_electronversion}/g
        s/@appname@/${pkgname%-bin}/g
        s/@runname@/app.asar/g
        s/@cfgdirname@/${_appname}/g
        s/@options@/env ELECTRON_OZONE_PLATFORM_HINT=auto/g
    " "${srcdir}/${pkgname%-bin}.sh"
    ar x "${srcdir}/${pkgname%-bin}-${pkgver}-x86_64.deb"
    _data_archive="$(ls data.tar.* 2>/dev/null | head -n1)"
    if [[ -z "${_data_archive}" ]]; then
        echo "Missing data.tar.* in deb archive"
        return 1
    fi
    bsdtar -xf "${_data_archive}"
    _get_electron_version
    sed -i -e "
        s|Exec=.*|Exec=${pkgname%-bin} %U|g
        s|Icon=.*|Icon=${pkgname%-bin}|g
    " "${srcdir}/usr/share/applications/feishin.desktop"
    _electron_target="${_elec_ver:-${_electronversion}.0.0}"
    _asar_src="${srcdir}/app.asar.unpacked"
    _asar_unpacked="${srcdir}/app.asar.unpacked.runtime"
    asar e "${srcdir}/opt/Feishin/resources/app.asar" "${_asar_src}"
    find "${_asar_src}/out" -type f -exec sed -i "s/process.resourcesPath/'\/usr\/lib\/${pkgname%-bin}'/g" {} +
    mkdir -p "${srcdir}/npm-home" "${_asar_unpacked}"
    (
        cd "${_asar_src}"
        HOME="${srcdir}/npm-home" npm rebuild abstract-socket \
            --build-from-source \
            --runtime=electron \
            --target="${_electron_target}" \
            --disturl=https://electronjs.org/headers
    ) || return 1
    if [[ -d "${_asar_src}/node_modules/abstract-socket/build" ]]; then
        mkdir -p "${_asar_unpacked}/node_modules/abstract-socket"
        cp -r "${_asar_src}/node_modules/abstract-socket/build" \
            "${_asar_unpacked}/node_modules/abstract-socket/"
    fi
    asar p "${_asar_src}" "${srcdir}/app.asar"
    if [[ -d "${srcdir}/opt/Feishin/resources/assets" ]]; then
        find "${srcdir}/opt/Feishin/resources/assets" -type d -exec chmod 755 {} +
    fi
}

package() {
    install -Dm755 "${srcdir}/${pkgname%-bin}.sh" "${pkgdir}/usr/bin/${pkgname%-bin}"
    install -Dm644 "${srcdir}/app.asar" -t "${pkgdir}/usr/lib/${pkgname%-bin}"
    if [[ -d "${srcdir}/app.asar.unpacked.runtime" ]]; then
        cp -Pr --no-preserve=ownership "${srcdir}/app.asar.unpacked.runtime" \
            "${pkgdir}/usr/lib/${pkgname%-bin}/app.asar.unpacked"
    fi
    if [[ -d "${srcdir}/opt/Feishin/resources/assets" ]]; then
        cp -Pr --no-preserve=ownership "${srcdir}/opt/Feishin/resources/assets" "${pkgdir}/usr/lib/${pkgname%-bin}"
    fi
    if [[ -d "${srcdir}/opt/Feishin/lib" ]]; then
        install -Dm644 "${srcdir}/opt/Feishin/lib/"* -t "${pkgdir}/usr/lib/${pkgname%-bin}/lib"
    fi
    _icon_sizes=(16x16 24x24 32x32 48x48 64x64 128x128 256x256 512x512)
    for _icons in "${_icon_sizes[@]}"; do
        if [[ -f "${srcdir}/usr/share/icons/hicolor/${_icons}/apps/feishin.png" ]]; then
            install -Dm644 "${srcdir}/usr/share/icons/hicolor/${_icons}/apps/feishin.png" \
                "${pkgdir}/usr/share/icons/hicolor/${_icons}/apps/${pkgname%-bin}.png"
        fi
    done
    install -Dm644 "${srcdir}/usr/share/applications/feishin.desktop" "${pkgdir}/usr/share/applications/${pkgname%-bin}.desktop"
}
