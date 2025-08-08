/*

  */
#ifndef __LED_H__
#define __LED_H__

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Define blinking type and priority.
 *
 */
typedef enum {
    BLINK_DOUBLE = 0,
    BLINK_TRIPLE,
    BLINK_FAST,
    BLINK_SLOW,
    BLINK_OFF,
    BLINK_MAX,
}led_state_t;

enum {
    LED_RED = 0,
    LED_GREEN,
    LED_MAX,
};

void led_init(void);

void led_start_state(int led_id, led_state_t state);
void led_stop_state(int led_id, led_state_t state);


#ifdef __cplusplus
}
#endif

#endif
