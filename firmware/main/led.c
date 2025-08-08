/*
 * SPDX-FileCopyrightText: 2023-2024 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <stdio.h>
#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "led_indicator.h"
#include "board.h"
#include "led.h"

static const char *TAG = "led";
static led_indicator_handle_t green_led_handle = NULL;
static led_indicator_handle_t red_led_handle = NULL;


/**
 * @brief Blinking twice times has a priority level of 0 (highest).
 *
 */
static const blink_step_t double_blink[] = {
    {LED_BLINK_HOLD, LED_STATE_ON, 100},
    {LED_BLINK_HOLD, LED_STATE_OFF, 100},
    {LED_BLINK_HOLD, LED_STATE_ON, 100},
    {LED_BLINK_HOLD, LED_STATE_OFF, 100},
    {LED_BLINK_HOLD, LED_STATE_OFF, 600},
    {LED_BLINK_LOOP, 0, 0},
};

/**
 * @brief Blinking three times has a priority level of 1.
 *
 */
static const blink_step_t triple_blink[] = {
    {LED_BLINK_HOLD, LED_STATE_ON, 500},
    {LED_BLINK_HOLD, LED_STATE_OFF, 500},
    {LED_BLINK_HOLD, LED_STATE_ON, 500},
    {LED_BLINK_HOLD, LED_STATE_OFF, 500},
    {LED_BLINK_HOLD, LED_STATE_ON, 500},
    {LED_BLINK_HOLD, LED_STATE_OFF, 500},
    {LED_BLINK_LOOP, 0, 0},
};

static const blink_step_t fast_blink[] = {
    {LED_BLINK_HOLD, LED_STATE_ON, 200},
    {LED_BLINK_HOLD, LED_STATE_OFF, 200},
    {LED_BLINK_LOOP, 0, 0},
};


static const blink_step_t slow_blink[] = {
    {LED_BLINK_HOLD, LED_STATE_ON, 100},
    {LED_BLINK_HOLD, LED_STATE_OFF, 1000},
    {LED_BLINK_LOOP, 0, 0},
};



/**
 * @brief Fast blinking has lowest priority.
 *
 */
static const blink_step_t off_blink[] = {
    // {LED_BLINK_HOLD, LED_STATE_ON, 100},
    {LED_BLINK_HOLD, LED_STATE_OFF, 500},
    {LED_BLINK_LOOP, 0, 0},
};

static blink_step_t const *led_mode[] = {
    [BLINK_DOUBLE] = double_blink,
    [BLINK_TRIPLE] = triple_blink,
    [BLINK_FAST] = fast_blink,
    [BLINK_SLOW] = slow_blink,
    [BLINK_OFF] = off_blink,
    [BLINK_MAX] = NULL,
};


void led_init(void)
{
    led_indicator_gpio_config_t gpio_config = {
        .gpio_num = BOARD_IO_LED_GREEN,
        .is_active_level_high = 1,
    };
    const led_indicator_config_t config = {
        .mode = LED_GPIO_MODE,
        .led_indicator_gpio_config = &gpio_config,
        .blink_lists = led_mode,
        .blink_list_num = BLINK_MAX,
    };
    green_led_handle = led_indicator_create(&config);
    assert(green_led_handle != NULL);

    gpio_config.gpio_num = BOARD_IO_LED_RED;
    red_led_handle = led_indicator_create(&config);
    assert(red_led_handle != NULL);

    led_indicator_start(green_led_handle, BLINK_SLOW);
    led_indicator_start(red_led_handle, BLINK_OFF);
}

void led_start_state(int led_id, led_state_t state)
{
    if (led_id == LED_GREEN) {
        led_indicator_start(green_led_handle, state);
    } else if (led_id == LED_RED) {
        led_indicator_start(red_led_handle, state);
    }
}

void led_stop_state(int led_id, led_state_t state)
{
    if (led_id == LED_GREEN) {
        led_indicator_stop(green_led_handle, state);
    } else if (led_id == LED_RED) {
        led_indicator_stop(red_led_handle, state);
    }
}
