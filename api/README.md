# G-Helper Profile Lab API

`ghelper.optiwork.co.kr`에서 운영하는 Cloudflare Worker입니다. `worker.mjs`, 읽기 전용 웹 화면 `site.mjs`, D1 바인딩 `DB`를 사용합니다. npm 런타임 의존성은 없으며 `node:crypto`는 Workers의 `nodejs_compat` 내장 기능으로 사용합니다. 자료실은 웹에서 둘러볼 수 있고 설정 적용·게시 기능은 Windows 앱에 있습니다.

## 실행과 구성

로컬 검증은 Node 22.13 이상에서 `npm test` 또는 `node --test test/worker.test.mjs`로 실행합니다. Node의 `node:sqlite`로 실제 `schema.sql`과 SQL을 검증합니다. 테스트의 얇은 어댑터는 D1의 `prepare/bind/first/all/batch` 호출 형태만 제공하며, SQLite 쿼리·제약·트랜잭션을 모사하지 않습니다.

`wrangler.jsonc`는 설정 예시입니다. `database_id`에는 자리 표시자만 있습니다. 승인된 배포 단계에서 실제 D1 ID와 원하는 custom domain을 지정해야 합니다. `schema.sql`은 새 DB용 스키마이며 기존 Sites DB의 자동 마이그레이션이 아닙니다.

| 바인딩/변수 | 용도 |
| --- | --- |
| `DB` | 이 패키지의 스키마가 적용된 Cloudflare D1 |
| `SERVICE_ORIGIN` | 정확한 허용 Origin. 기본값 `https://ghelper.optiwork.co.kr` |
| `RELEASE_URL` | HTTPS GitHub 배포 링크. 비어 있으면 다운로드 미설정 안내 |

`GET /`는 프로그램 설명, 다운로드 링크와 공개 설정 자료실을 제공합니다. 웹 화면은 같은 출처의 `GET /api/profiles`를 읽어 사용자 게시물을, `GET /api/references`를 읽어 출처가 있는 공식 사양·커뮤니티 Time Spy 참고 기록을 표시합니다. 같은 검색창에서 모델·연도·CPU·GPU를 찾습니다. 참고 기록은 적용 가능한 설정 파일이 아닙니다. `GET /site.css`, `GET /site.js`는 웹 화면 자산입니다. 웹에는 설정 적용·게시 요청이 없습니다.

## API 계약

게시물·오류 JSON 응답은 `Cache-Control: no-store`이고 정적 참고 목록만 `public, max-age=300`입니다. 오류는 `{ "error": "사용자 메시지", "code": "machine_code" }`입니다. 허용되지 않은 Origin은 403입니다. Origin 없는 네이티브 요청과 정확한 서비스 Origin은 허용합니다. 브라우저의 임의 출처를 허용하는 CORS 헤더는 보내지 않습니다. OPTIONS는 405이며 Python 네이티브 중계는 preflight가 필요하지 않습니다. Origin 검사는 사용자 인증 수단이 아닙니다.

| 요청 | 성공 응답 |
| --- | --- |
| `GET /api/health` | `200 {ok:true,service:"ghelper-profile-api",schemaVersion:1}`. DB 스키마 읽기도 확인 |
| `GET /api/references` | `200 {schemaVersion:2,updatedAt,entries:[...]}`. 출처가 있는 읽기 전용 참고 기록 |
| `GET /api/profiles?model=&q=&cursor=&limit=30` | `200 {posts:[...],nextCursor:null 또는 문자열}` |
| `GET /api/profiles/{uuid}` | `200 {post:{...}}` |
| `POST /api/profiles` | 최초 `201 {id,createdAt,replayed:false}`, 재시도 `200 {id,createdAt,replayed:true}` |
| `DELETE /api/profiles/{uuid}` | `200 {deleted:true}` |

목록과 상세의 post는 정규화된 공유 bundle 최상위에 `id`, `createdAt`을 더한 형식입니다. 삭제 키, 삭제 해시, 요청 키, 내부 payload 해시는 공개하지 않습니다. `createdAt`은 서버가 생성한 UTC ISO 날짜입니다. 목록 순서는 `createdAt DESC, id DESC`이며 같은 밀리초의 게시물도 중복·누락 없이 페이지를 이어갑니다.

`q`는 앱 내 검색어(최대 160자, 12개 단어)이며 공유된 모델 코드·제품군 별칭·연도·프로필 이름·메모·CPU·GPU·메모리를 찾습니다. `RTX5090`과 `RTX 5090` 모두 검색할 수 있습니다. 이름이 등록된 ASUS 모델만 `G16 2025` 같은 제품군으로 확장하며, GPU 조건도 실제 게시 사양과 맞아야 합니다. 검색 조건은 다음 페이지 커서에 묶입니다. `model`은 양끝 공백을 제거한 정확한 대소문자 구분 일치입니다. 비어 있거나 생략하면 전체 모델입니다. 모델 길이는 200 UTF-16 코드 단위 이하입니다. `limit`은 1~30이며 기본 30입니다. 알 수 없는 쿼리 이름, 중복 쿼리 이름, 범위 밖 limit은 400입니다. 처음 요청에서는 cursor를 생략하세요. 이후 서버가 준 커서를 그대로 사용하고 model 필터를 유지하세요. 다음 페이지가 없으면 `nextCursor`는 null입니다. UUID는 소문자 표준 8-4-4-4-12 형식, 버전 1~8, RFC variant를 허용합니다. 새 요청 키는 UUIDv4가 적합합니다.

### 게시와 네트워크 재시도

클라이언트는 공개할 모델·작성자·메모·설정·점수를 사용자에게 보여주고 공개 확인을 받은 후 POST를 보냅니다. 이 Worker는 UI 확인 상태를 대신 판단하지 않습니다.

POST는 `Content-Type: application/json`과 다음 헤더 두 개가 필수입니다.

```text
Idempotency-Key: <클라이언트가 생성한 소문자 UUID>
X-Delete-Token: <암호학적 난수 32바이트를 표현한 소문자 hex 64자>
```

Python에서는 `str(uuid.uuid4())`, `secrets.token_hex(32)`로 만들 수 있습니다. **네트워크 전송 전에** 요청 키·삭제 키·공유 bundle을 로컬 pending 영수증에 저장하세요. 성공 응답이 유실되면 같은 세 항목으로 재시도하면 됩니다. 서버는 raw 삭제 키를 저장하거나 돌려주지 않으므로 클라이언트가 처음부터 보관해야 합니다.

본문은 기존 `ghelper-profile-share` schemaVersion 1 bundle입니다. 검증기가 정규화한 결과를 객체 키 순서와 무관한 canonical JSON으로 저장하고 요청 해시를 계산합니다. 동일 요청 키와 동일 정규화 payload·삭제 키의 재시도는 같은 id·생성일을 반환합니다. payload 또는 삭제 키가 달라지면 409 `idempotency_conflict`입니다. 삭제된 요청 키의 재전송은 410 `already_deleted`이며 새 게시물을 만들지 않습니다. 의도적으로 다시 게시하려면 새 요청 키와 삭제 키를 생성하세요.

### 삭제

DELETE 본문은 `{ "deleteToken": "64자리 소문자 hex" }`만 허용하며 최대 1KiB입니다. 올바른 키로 이미 삭제한 게시물을 다시 삭제해도 200으로 응답합니다. 없는 id와 잘못된 삭제 키는 모두 404입니다. 이 키를 가진 사람이 삭제할 수 있으며 잃어버린 키의 복구 API는 없습니다.

## 검증과 저장 한도

- 요청 body는 실제 읽은 UTF-8 바이트 기준 128KiB 이하입니다. Content-Length만 신뢰하지 않고 스트림을 읽는 동안 제한합니다. 정규화 후 저장 payload도 128KiB 이하이며 DB CHECK로 다시 제한합니다.
- 한 목록 응답은 최대 30개이고 JSON 응답 전체는 4MiB 이하입니다. 필터·커서 쿼리는 바인딩된 SQL 매개변수를 사용합니다.
- 원래 `ProfileLibrary/lib/validation.ts`의 엄격한 필드 허용 목록, 정수 범위, 단조 증가 팬 곡선, 설정 해시, 점수의 설정 해시 연결, 기본 mode 0/1/2 및 최대 20개 결과 제한을 유지합니다.
- 허용하지 않는 시스템 정보·파일 경로 등의 필드는 거부합니다. `verification`은 입력 주장과 관계없이 항상 `user-reported`로 저장합니다.
- **settingsHash는 설정·결과의 내부 일관성 확인용 SHA-256이며 암호 서명이나 벤치마크 진위 증명이 아닙니다.** 게시자, 기기, 점수의 진위와 설정 안전성을 보증하지 않습니다.
- 시간별 `SHA-256(hour + ':' + CF-Connecting-IP)`로 만든 키당 신규 게시 20건입니다. IP 원문은 DB와 앱 로그에 저장하지 않습니다. Cloudflare 헤더가 없으면 공유 버킷을 사용합니다. 이는 인증·고급 봇 방지 기능이 아니며 NAT 사용자들은 한도를 공유할 수 있습니다.
- 신규 영수증·게시물·한도 증가는 한 번의 D1 batch 트랜잭션으로 처리합니다. 동시 동일 요청은 하나만 삽입하며 재시도·충돌 요청은 한도를 추가로 쓰지 않습니다. 한도 초과는 429와 Retry-After 초를 반환합니다.
- 오래된 시간 버킷은 POST 시 정리합니다. 삭제 뒤에도 중복 게시를 막기 위해 요청 영수증의 키·해시·id·시간은 남기고 공개 payload는 삭제합니다. 영수증 자동 만료는 없습니다.
- 로그에는 고정된 장애 이벤트만 남기며 body·삭제 키·IP·DB 오류 원문은 기록하지 않습니다.

기타 상태: 400 검증·JSON·쿼리 오류, 403 Origin 거부, 404 없음, 405 메서드 미지원, 413 크기 초과, 415 Content-Type 오류, 503 DB·구성 장애. 삭제·게시 요청의 HTTP 불확실성은 로컬 영수증을 유지하여 같은 요청으로 재시도하세요.

## 검증 범위

Node/SQLite 회귀 테스트는 동시 재시도, 20건 한도, 트랜잭션 실패 롤백, 삭제 재시도와 삭제 후 재게시 방지, Unicode 모델 커서, 크기 한도, 비공개 필드 거부와 점수 바인딩, Origin·HTTP 오류, 공개 웹 화면·자산을 검증합니다. 운영 서버 게시·삭제까지 수행한 통합 검증은 아닙니다.

현재 공식 문서 확인일: 2026-09-24.

- [Workers 권장 사항](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)에 따라 요청 크기 제한, DB 바인딩, 명시적 오류 처리를 사용합니다.
- [D1 batch](https://developers.cloudflare.com/d1/worker-api/d1-database/#batch)의 트랜잭션 보장과 [prepared statements](https://developers.cloudflare.com/d1/worker-api/prepared-statements/)를 사용합니다.
- [Wrangler 설정](https://developers.cloudflare.com/workers/wrangler/configuration/)에 따라 JSONC·D1 바인딩·compatibility date를 지정합니다.
