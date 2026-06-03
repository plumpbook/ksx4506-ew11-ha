# EW11 설정 가이드

## 네트워크
- 모드: TCP Server
- 포트: 8899 (권장)
- 고정 IP 권장

## 보안
- EW11 TCP 포트는 인터넷에 직접 노출하지 마세요.
- 공유기 포트포워딩으로 EW11을 외부에 열지 마세요.
- Home Assistant가 있는 내부망에서만 접근하도록 방화벽이나 VLAN으로 제한하는 것을 권장합니다.
- 원격 접속이 필요하면 Tailscale, WireGuard 같은 VPN을 사용하고 EW11 포트에는 HA 호스트만 접근하도록 ACL을 설정하세요.
- 테스트용 HA와 실제 HA가 같은 EW11에 동시에 연결되지 않도록 하세요.

## 시리얼
- Baud/Parity/Stop bit: 월패드 버스와 동일
- 일반적으로 9600 8N1 시작 후 실측 보정

## 권장 옵션
- Nagle/packet merge 비활성
- Keepalive 활성
- Serial timeout 짧게(프레임 지연 최소화)

## 연결 점검
1. EW11과 HA 호스트 간 ping 확인
2. `nc <EW11_IP> 8899` 연결 확인
3. 통합 등록 후 `Unsupported Packets` 진단 센서나 HA 로그에서 frame 유입 확인
