# font-project

한국어·일본어·영어를 위한 독립 고정폭 Nerd Font 개발 프로젝트입니다. 최종 글꼴 이름은 아직 결정하지 않았습니다.

## 설계 목표

- Sarasa Fixed J (Iosevka + Source Han Sans) 기반, CJK 자형의 비례와 일본식 기본 한자 자형 보존
- 영문 반각 / CJK 전각 1:2, 코딩 리가처 제외, 반각 em dash
- Material Design Icons를 포함한 Nerd Fonts 아이콘 전체 지원 목표
- 추가 아이콘의 advance width는 반각 1칸, 실제 윤곽도 셀을 넘지 않도록 검증
- Windows Terminal, VS Code, Chrome, 메모장 등에서 단일 TTF 패밀리로 사용
- 기존 한글·가나·한자 및 IVS(이체자 시퀀스)를 자동으로 삭제하지 않음

## 상태

초기 개발 환경입니다. 설치 가능한 최종 글꼴이나 공개 릴리스는 아직 없습니다. 전체 아이콘이 65,535 글리프 제한 내에 들어가는지 실측하고, 필요한 경우 명시적으로 서브세팅 정책을 결정해야 합니다.

## 시작하기 (Ubuntu / WSL)

```bash
sudo apt update
sudo apt install -y python3 python3-venv fontforge python3-fontforge p7zip-full
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/project.py fetch
python scripts/project.py inspect
python -m unittest discover -s tests -v
python scripts/project.py build --style Regular
```

기본 빌드는 잠긴 버전의 Sarasa 및 Nerd Fonts 공식 패처를 사용합니다. 원본 글꼴과 아이콘 수를 검사하고 전체 패치의 용량·너비·윤곽 검증에 실패하면 배포 가능한 결과물을 생성하지 않습니다. 다운로드한 원본, 임시 빌드, 출력 TTF는 Git에 커밋하지 않습니다.

`Font Project Mono`는 개발용 임시 패밀리 이름입니다. 최종 이름과 라이선스 고지는 릴리스 전에 확정합니다.

- [설계 및 작업 순서](docs/DESIGN.md)
- [고정된 upstream 입력](config/sources.json)
- [라이선스 관리](LICENSES/README.md)
- [렌더링 시험 텍스트](tests/specimen.txt)
