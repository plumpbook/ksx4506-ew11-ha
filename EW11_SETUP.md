# EW11 설정 가이드

## 네트워크
- 모드: TCP Server
- 포트: 8899 (권장)
- 고정 IP 권장

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
3. 통합 등록 후 unknown diagnostic 센서에서 frame 유입 확인
