# Release Notes

## v0.2.17
- HA 시작 직후 장치가 상태 요청에 즉시 응답하지 않는 경우에도 조명/콘센트가 `unknown`으로 남지 않도록 마지막 HA `on/off` 상태를 복원합니다.
- 복원값은 임의 기본값이 아니며, 이후 실제 KS X 4506 상태 패킷이 수신되면 기존 discovery/decode 경로로 덮어씁니다.

## v0.2.16
- HA 시작 직후 복원된 조명/콘센트 상태가 `unknown`으로 남는 시간을 줄이기 위해, 알려진 장치 상태 probe를 단발 요청에서 응답 수신까지 재시도하는 방식으로 변경했습니다.
- startup probe가 장치별 상태 응답 command를 확인하도록 보강해 실제 상태 프레임이 들어온 경우에만 엔티티 상태가 갱신되도록 유지했습니다.

## v0.2.15
- HA 재시작 후 조용한 장치의 상태 패킷이 아직 들어오지 않아 기존 유효 엔티티가 `unavailable`로 남는 문제를 수정했습니다.
- 기존 HA entity/device registry의 KS X 4506 key를 시작 시 복원하고, 복원된 조명/콘센트/센서 상태를 한 번 probe하도록 보강했습니다.
- 복원된 조명은 실제 상태 수신 전까지 임의로 꺼짐 처리하지 않고 `unknown` 상태로 유지합니다.

## v0.2.14
- `EW11 Link` 진단 센서가 새 패킷 수신 없이도 연결 상태 변화를 즉시 반영하도록 수정했습니다.
- EW11 수신이 `stale` 또는 `disconnected`로 바뀐 경우 HA 화면에 이전 `receiving` 상태가 남지 않도록 coordinator 갱신 경로를 보강했습니다.
- 연결 상태 변화만 발생하는 상황을 검증하는 회귀 테스트를 추가했습니다.

## v0.2.13
- EW11 TCP 연결이 살아 있는 것처럼 보이지만 RX가 장시간 멈춘 경우 자동으로 연결을 닫고 재연결하도록 수정했습니다.
- 일반 엔티티를 `unavailable`로 바꾸는 짧은 stale 기준은 20초로 유지하고, TCP 재연결 기준은 120초로 분리했습니다.
- `EW11 Link` 진단 속성에 `rx_reconnect_after`를 추가해 재연결 기준을 확인할 수 있게 했습니다.

## v0.2.12
- EW11 수신 상태가 `receiving`이 아닐 때 일반 KS X 4506 엔티티를 `unavailable`로 표시하도록 변경했습니다.
- 기본 RX stale 기준을 120초에서 20초로 낮춰 전력/누적 센서가 데이터 공백 동안 마지막 값을 오래 유지하지 않도록 개선했습니다.
- EW11 진단 센서는 계속 노출되어 연결 상태와 stale 원인을 확인할 수 있습니다.

## v0.2.11
- EW11 수신이 조용한 상태를 TCP 단절로 판단해 재연결을 반복하던 동작을 수정했습니다.
- 수신 정지 상태에서는 연결을 유지하고 `EW11 Link` 진단 상태만 `stale`로 표시합니다.
- EW11 접속 timeout 로그가 실제 접속 실패인지 더 명확히 보이도록 보강했습니다.

## v0.2.10
- EW11 TCP 연결 상태를 확인할 수 있는 `EW11 Link` 진단 센서를 추가했습니다.
- 마지막 RX 시각, RX 정지 시간, stale 기준, 마지막 연결 오류를 diagnostics에 포함했습니다.
- EW11 수신이 일정 시간 멈춘 경우 stale 상태로 보고 재연결을 시도하도록 보강했습니다.
- 제어 명령이 최종 실패한 경우 debug가 아닌 warning 로그로 남기도록 변경했습니다.

## v0.2.9
- `0x33` 현관 패널에 `Elevator Status` 센서를 추가했습니다.
- `0x33/0x43` 이벤트 응답을 해석해 엘리베이터 호출 승인(`calling`)과 도착(`arrived`) 이벤트를 노출합니다.
- 반복 이벤트 자동화를 위해 `last_panel_event_seq` 속성을 추가했습니다.
- README와 관측 인벤토리에 현관 패널 엘리베이터 이벤트 설명을 보강했습니다.

## v0.2.8
- `Unsupported Packets`와 `Packet Capture` 센서 속성에 사람이 읽기 쉬운 summary/signature 필드를 추가했습니다.
- 최근 unsupported/candidate 패킷과 반복 횟수가 많은 signature를 별도 속성으로 볼 수 있게 했습니다.
- raw/payload 샘플은 계속 기본 redacted 상태를 유지하고, 옵션을 켠 경우에만 포함합니다.

## v0.2.7
- 일반 센서 계열의 auxiliary/주기성 패킷이 unsupported 카운터를 불필요하게 증가시키지 않도록 필터링했습니다.
- 지원 가능성이 있는 패킷은 자동 장치 생성 대신 candidate 진단으로 유지하도록 discovery 정책을 정리했습니다.

## v0.2.6
- 콘센트 계열 auxiliary 패킷이 unsupported 카운터를 불필요하게 증가시키지 않도록 필터링했습니다.
- `0x39` 콘센트 패킷 분류가 supported/candidate/unsupported로 더 명확히 나뉘도록 보정했습니다.

## v0.2.5
- `Packet Capture` 센서에 수신 패킷 분류를 추가했습니다.
- 캡처 결과에서 `supported`, `ignored_request`, `candidate`, `unsupported`를 구분해서 볼 수 있게 했습니다.
- `latest_unsupported_signature`와 `latest_candidate_signature` 기반으로 짧은 실측 캡처를 확인할 수 있게 했습니다.

## v0.2.4
- Home Assistant config/options flow schema 직렬화 오류를 수정했습니다.
- packet capture filter 옵션이 HA 프론트엔드에서 안정적으로 표시되고 저장되도록 보정했습니다.

## v0.2.3
- HA 전체 debug 로그 대신 짧은 실측에 사용할 수 있는 `packet_capture_enabled`, `packet_capture_filter`, `packet_capture_limit` 옵션을 추가했습니다.
- 주기적인 bus polling request가 unsupported report를 오염시키지 않도록 ignored request로 분류했습니다.
- 공개 배포 아티팩트에 로컬 IP, 개인 호스트명, NAS 경로 같은 환경 정보가 들어가지 않도록 테스트를 추가했습니다.
- 미지원 패킷 제보 흐름과 개인정보 제거 안내를 문서화했습니다.

## v0.2.2
- 등록된 EW11 항목의 `timeout`, `retry`, `max_attempts`, `gas_unlock`, `expose_packet_samples`를 `구성`/`Options` 화면에서 변경할 수 있게 했습니다.
- Options 값이 기존 등록값보다 우선 적용되도록 coordinator, diagnostics, `Unsupported Packets` 센서를 정리했습니다.
- 옵션 변경 후 config entry를 자동 reload해서 재등록 없이 새 설정이 적용되도록 했습니다.
- `expose_packet_samples`는 기본값을 계속 `false`로 유지하고, 필요할 때만 명시적으로 켤 수 있게 했습니다.

## v0.2.1
- 기본 diagnostics와 `Unsupported Packets` 센서 속성에서 raw/payload 패킷 샘플을 숨기도록 변경했습니다.
- raw 패킷 샘플이 필요한 경우에만 `expose_packet_samples` 옵션으로 명시적으로 노출할 수 있게 했습니다.
- 패리티 실패와 공동현관 이벤트 로그에서 raw 패킷이 기본 로그에 남지 않도록 정리했습니다.
- 미지원/후보 패킷이 장치로 자동 생성되지 않도록 discovery gating을 강화했습니다.
- 기존에 생성된 legacy/orphaned registry 항목 정리를 보강했습니다.
- EW11 설정값의 host, port, timeout, retry, STX/ETX 검증을 강화했습니다.
- EW11 포트 외부 노출 금지와 공개 이슈 raw 패킷 공유 주의사항을 문서에 추가했습니다.

## v0.2.0
- HACS 설치와 업데이트에 맞춘 저장소 메타데이터와 문서를 정리했습니다.
- 조명, 콘센트, 난방, 가스, 계량, 현관, 공동현관 장치의 자동 발견과 엔티티 이름을 정리했습니다.
- 미지원 패킷은 자동 장치 생성 대신 `Unsupported Packets` 진단 센서와 diagnostics JSON에 기록하도록 변경했습니다.
- 기존에 생성된 unknown 장치와 엔티티는 config entry 삭제 시 registry cleanup으로 제거되도록 개선했습니다.
- 조명 그룹 상태 패킷을 채널별 상태로 분해하고, 개별 조명 제어 시 기존 채널 상태를 보존하도록 보정했습니다.
- 콘센트 그룹 패킷을 개별 채널 상태로 분해하도록 개선했습니다.
- ACK/상태 확인 기반 명령 재시도 흐름을 추가했습니다.

## v0.1.0
- EW11 TCP 수신/재연결 기본 구현
- KS X 4506 프레임 파서/빌더 기본 구현
- Home Assistant 커스텀 인티그레이션 초기 버전
- light/switch/climate/fan/sensor 플랫폼 초안
- unknown diagnostic 센서 추가
- 가스밸브 안전가드(기본 차단) 적용

## Known gaps
- 실환경 캡처 기반 cmd/type 매핑 정밀화 필요
- ACK/NAK 시맨틱은 벤더 구현별 보정 필요
- 장치별 payload 디코딩 룰 확장 필요
