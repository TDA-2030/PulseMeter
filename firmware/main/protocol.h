#pragma once
#include <stdint.h>

// Frame magic bytes (unchanged from v1 for easy wireshark filtering)
#define PROTO_MAGIC0  0x23
#define PROTO_MAGIC1  0x35

// Message types
#define MSG_STREAM     0x01  // Host → Device: push meter values (no response)
#define MSG_READ_REQ   0x02  // Host → Device: read a device parameter
#define MSG_READ_RSP   0x03  // Device → Host: read response
#define MSG_WRITE_REQ  0x04  // Host → Device: write a device parameter
#define MSG_WRITE_RSP  0x05  // Device → Host: write acknowledgement

// Response status codes
#define PROTO_STATUS_OK       0x00
#define PROTO_STATUS_ERR      0x01  // General error / read-only violation
#define PROTO_STATUS_UNKNOWN  0x02  // Unknown param_id

// Parameter IDs
#define PARAM_METER1_MAX_DUTY  0x0001  // uint32, rw — PWM duty ceiling for meter 1
#define PARAM_METER2_MAX_DUTY  0x0002  // uint32, rw — PWM duty ceiling for meter 2
#define PARAM_MODE             0x0003  // uint8,  rw — persisted in NVS
#define PARAM_METER1_VALUE     0x0010  // uint8,  ro — current percent 0-100
#define PARAM_METER2_VALUE     0x0011  // uint8,  ro — current percent 0-100

// Additional read-only parameter IDs
#define PARAM_FIRMWARE_VERSION 0x0004  // uint32, ro - 0x00MMmmpp (major/minor/patch)

// Frame layout constants
#define PROTO_HEADER_SIZE  6   // magic(2) + type(1) + seq(1) + len(2 big-endian)
#define PROTO_CRC_SIZE     1
#define PROTO_MAX_PAYLOAD  32  // max payload bytes (generous headroom)

/**
 * CRC8: XOR of type, seq, both length bytes, then every payload byte.
 * Simple, fast, and sufficient for small trusted-network frames.
 */
static inline uint8_t proto_crc8(uint8_t type, uint8_t seq,
                                  uint16_t len, const uint8_t *payload)
{
    uint8_t crc = type ^ seq ^ (uint8_t)(len >> 8) ^ (uint8_t)(len & 0xFF);
    for (uint16_t i = 0; i < len; i++) {
        crc ^= payload[i];
    }
    return crc;
}
