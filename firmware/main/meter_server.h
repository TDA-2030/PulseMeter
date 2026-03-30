#pragma once
#include <cstdint>
#include <lwip/sockets.h>
#include "protocol.h"

/**
 * TCP server that drives meter dials from framed protocol messages.
 *
 * Supported message flows:
 *   Host → Device  MSG_STREAM    — real-time meter value push (fire-and-forget)
 *   Host → Device  MSG_READ_REQ  — read a device parameter
 *   Device → Host  MSG_READ_RSP  — parameter value response
 *   Host → Device  MSG_WRITE_REQ — write a device parameter
 *   Device → Host  MSG_WRITE_RSP — write acknowledgement
 */
class MeterServer {
public:
    MeterServer();

    bool startServer();

private:
    bool waitForClient();

    // Low-level frame I/O
    bool recvFrame(uint8_t &type, uint8_t &seq, uint8_t *payload, uint16_t &len);
    bool sendFrame(uint8_t type, uint8_t seq, const uint8_t *payload, uint16_t len);

    // Message handlers
    void handleStream   (const uint8_t *payload, uint16_t len);
    void handleReadReq  (uint8_t seq, const uint8_t *payload, uint16_t len);
    void handleWriteReq (uint8_t seq, const uint8_t *payload, uint16_t len);

    uint16_t port_;
    int listen_fd;
    int client_fd;

    // Last-known meter values, returned for PARAM_METERn_VALUE reads
    uint8_t meter_value_[2];
};
