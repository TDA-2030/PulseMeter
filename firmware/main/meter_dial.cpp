/* LEDC (LED Controller) basic example

   This example code is in the Public Domain (or CC0 licensed, at your option.)

   Unless required by applicable law or agreed to in writing, this
   software is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
   CONDITIONS OF ANY KIND, either express or implied.
*/
#include <stdio.h>
#include <math.h>
#include <algorithm>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/timers.h"
#include "driver/ledc.h"
#include "esp_timer.h"
#include "esp_err.h"
#include "esp_log.h"
#include "meter_dial.h"
#include "board.h"
#include "led.h"

static const char *TAG = "motor";


/* Warning:
 * For ESP32, ESP32S2, ESP32S3, ESP32C3, ESP32C2, ESP32C6, ESP32H2, ESP32P4 targets,
 * when LEDC_DUTY_RES selects the maximum duty resolution (i.e. value equal to SOC_LEDC_TIMER_BIT_WIDTH),
 * 100% duty cycle is not reachable (duty cannot be set to (2 ** SOC_LEDC_TIMER_BIT_WIDTH)).
 */
bool PWM::init(int pin1)
{
#define LEDC_TIMER              LEDC_TIMER_0
#define LEDC_MODE               LEDC_LOW_SPEED_MODE
#define LEDC_DUTY_RES           LEDC_TIMER_12_BIT


    ESP_LOGI(TAG, "Initializing PWM...");
    // Prepare and then apply the LEDC PWM timer configuration
    ledc_timer_config_t ledc_timer = {
        .speed_mode       = LEDC_MODE,
        .duty_resolution  = LEDC_DUTY_RES,
        .timer_num        = LEDC_TIMER,
        .freq_hz          = (uint32_t)3000,
        .clk_cfg          = LEDC_AUTO_CLK,
        .deconfigure      = false,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&ledc_timer));

    // Prepare and then apply the LEDC PWM channel configuration
    ledc_channel_config_t ledc_channel = {
        .gpio_num       = 0,
        .speed_mode     = LEDC_MODE,
        .channel        = LEDC_CHANNEL_0,
        .intr_type      = LEDC_INTR_DISABLE,
        .timer_sel      = LEDC_TIMER,
        .duty           = 0, // Set duty to 0%
        .hpoint         = 0,
        .sleep_mode     = LEDC_SLEEP_MODE_NO_ALIVE_NO_PD,
        .flags          = {
            .output_invert = 0,
        },
    };

    int channel = LEDC_CHANNEL_0;

    ledc_channel.channel = (ledc_channel_t)channel;
    ledc_channel.gpio_num = pin1;
    ESP_ERROR_CHECK(ledc_channel_config(&ledc_channel));
    return 0;
}

void PWM::set_pwm(uint32_t duty)
{
    ledc_set_duty(LEDC_MODE, LEDC_CHANNEL_0, duty);
    ESP_ERROR_CHECK(ledc_update_duty(LEDC_MODE, LEDC_CHANNEL_0));
}

MeterDial::MeterDial(const char *_name): name(_name)
{
    
}

void MeterDial::init(int pwm_pin)
{
    pwm = new PWM();
    pwm->init(pwm_pin);
    pwm->set_pwm(0);
    max_duty = 450;
}

void MeterDial::set_percent(int percent)
{
    int32_t duty = std::clamp(percent, 0, 100);
    duty = duty * max_duty / 100;
    pwm->set_pwm(duty);
}

void MeterDial::enable(bool is_enable)
{


}
