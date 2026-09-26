# 개발과 Windows 빌드

저장소 구성은 `desktop/`의 Windows 앱, `api/`의 자료실 API, `scripts/build.ps1`의 배포 파일 빌드입니다. Windows 64비트 Python 3.14 이상과 Node.js 24를 사용합니다. 빌드에 쓰는 PyInstaller는 현재 확인한 **6.22.3**으로 고정했습니다. 앱의 직접 Python 의존성 버전은 `desktop/requirements.txt`에 있습니다.

## 소스 실행과 검사

저장소 루트의 PowerShell에서 실행합니다.

```powershell
python -m venv build/.venv
./build/.venv/Scripts/python.exe -m pip install -r desktop/requirements.txt

Push-Location desktop
try {
    ../build/.venv/Scripts/python.exe -m unittest discover -s tests -v
} finally {
    Pop-Location
}

node --test api/test/worker.test.mjs
node desktop/tests/settings-view-tests.cjs
node --test desktop/tests/score-card-tests.cjs

./build/.venv/Scripts/python.exe desktop/app.py --show
```

개발 중 기존 저장소와 분리하려면 앱에 `--data-dir`로 별도 로컬 폴더를 지정할 수 있습니다. 이 폴더의 설정·백업·결과·공유 영수증을 Git에 넣지 마세요. 테스트는 저장소 코드와 모의 동작을 확인하며 실제 노트북의 안정성이나 Time Spy 성능을 인증하지 않습니다.

## 배포 파일 생성

```powershell
./scripts/build.ps1
```

Python 실행 파일을 지정할 수도 있습니다.

```powershell
./scripts/build.ps1 -PythonExecutable 'C:\Python314\python.exe'
```

스크립트는 Python 3.14 이상·64비트 여부를 검사하고 `build/.venv`를 준비합니다. requirements와 고정 버전 PyInstaller를 설치한 뒤 `--onefile --noconsole`로 묶습니다. `desktop/web`, `desktop/catalog.json`, `desktop/app.ico`를 명시적으로 포함하며 `desktop/`을 모듈 검색 경로로 지정합니다. 중간 파일은 매번 새 `build/<ID>/`에 만들어 기존 중간 폴더를 삭제하지 않습니다.

결과는 다음과 같습니다.

- `dist/GHelperProfileLab.exe`
- `dist/GHelperProfileLab-windows-x64.zip`: 실행 파일, README, 데스크톱 Markdown 문서, Python·외부 라이브러리 라이선스 고지
- `dist/SHA256SUMS.txt`: 실행 파일 SHA-256

소스는 Git 저장소에서 별도로 제공합니다. ZIP은 전체 작업 폴더를 압축하지 않으며 지정한 실행 파일·문서·고지만 담습니다. 코드를 서명하거나 GitHub Release를 게시하지 않습니다. 배포 전에는 해당 버전의 기능 설명과 라이선스 고지가 최신인지 확인해야 합니다.

## CI와 API

`.github/workflows/build.yml`은 Windows에서 Python 전체 단위 테스트, Node API 회귀 테스트, 설정 화면 테스트를 통과한 뒤 빌드 결과를 Actions artifact로 올립니다. `contents: read` 권한만 사용하며 Release 생성과 Cloudflare 배포는 자동으로 실행하지 않습니다.

자료실의 운영 주소는 `https://ghelper.optiwork.co.kr`입니다. API 구현·스키마·요청 제한은 [api/README.md](api/README.md)에 있습니다. 로컬 API 테스트는 Node의 SQLite로 SQL과 트랜잭션을 검증합니다. 실계정의 D1 ID·도메인·배포 권한은 운영 담당자가 별도로 관리합니다.

빌드 옵션은 [PyInstaller 공식 문서](https://pyinstaller.org/en/stable/usage.html)를 기준으로 합니다. 외부 의존성의 고지는 [desktop/THIRD-PARTY-LICENSES.txt](desktop/THIRD-PARTY-LICENSES.txt), [desktop/STEAM-UI-LICENSES.txt](desktop/STEAM-UI-LICENSES.txt), [desktop/PYTHON-LICENSE.txt](desktop/PYTHON-LICENSE.txt)를 함께 배포합니다.
