# EW11 설정 가이드

## 네트워크
- 모드: TCP Server
- 포트: 8899 (권장)
- 고정 IP 권장
- Home Assistant 호스트에서 EW11 IP/포트로 직접 접근 가능해야 합니다.

## 보안
- EW11 TCP 포트는 인터넷에 직접 노출하지 마세요.
- 공유기 포트포워딩으로 EW11을 외부에 열지 마세요.
- Home Assistant가 있는 내부망에서만 접근하도록 방화벽이나 VLAN으로 제한하는 것을 권장합니다.
- 원격 접속이 필요하면 Tailscale, WireGuard 같은 VPN을 사용하고 EW11 포트에는 HA 호스트만 접근하도록 ACL을 설정하세요.
- 테스트용 HA와 실제 HA가 같은 EW11에 동시에 연결되지 않도록 하세요.

## 운영 HA와 테스트 HA
- 하나의 EW11에는 한 시점에 하나의 Home Assistant 인스턴스만 연결하는 것을 권장합니다.
- 운영 HA와 테스트 HA가 동시에 EW11 TCP socket에 붙으면 RS-485 request/response 순서가 꼬이거나 상태 패킷을 서로 나눠 받을 수 있습니다.
- 테스트가 필요한 경우 운영 HA의 통합 항목을 잠시 비활성화하거나, 테스트 HA를 먼저 종료한 뒤 운영 HA를 다시 연결하세요.
- 운영 HA에 적용하기 전 NAS나 별도 테스트 HA에서 검증할 수 있지만, 실제 EW11에 붙는 순간에는 단일 연결 원칙을 지켜야 합니다.

## 시리얼
- Baud/Parity/Stop bit: 월패드 버스와 동일
- 일반적으로 9600 8N1 시작 후 실측 보정

## 권장 옵션
- Nagle/packet merge 비활성
- Keepalive 활성
- Serial timeout 짧게(프레임 지연 최소화)
- EW11이 packet delimiter/merge 기능을 제공한다면 임의 병합보다 raw byte stream에 가깝게 설정하세요.

## 연결 점검
1. EW11과 HA 호스트 간 ping 확인
2. `nc <EW11_IP> 8899` 연결 확인
3. 통합 등록 후 `Unsupported Packets` 진단 센서나 HA 로그에서 frame 유입 확인

## 패킷 캡처 주의
- 평상시에는 HA 전체 debug 로그보다 통합의 `Packet Capture` 옵션을 사용하세요.
- `packet_capture_filter`를 `33` 또는 `40`처럼 좁히고, 필요한 동작을 한두 번만 실행한 뒤 다시 끄세요.
- `Packet Capture`는 raw frame을 센서 속성에 보관하므로 공개 공유 전에는 위치, 생활 패턴, 장치 구성이 드러나지 않는지 확인해야 합니다.
- `expose_packet_samples`는 unsupported/candidate 진단에 raw/payload 샘플을 포함합니다. 기본값은 보안을 위해 `false`입니다.
