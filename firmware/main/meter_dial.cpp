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

int PWM::channel_cnt = (int) LEDC_CHANNEL_0;

bool PWM::init(int pin1)
{
#define LEDC_TIMER              LEDC_TIMER_0
#define LEDC_MODE               LEDC_LOW_SPEED_MODE
#define LEDC_DUTY_RES           LEDC_TIMER_12_BIT

    ESP_LOGI(TAG, "Initializing PWM channel %d on pin %d", channel_cnt, pin1);
    channel = channel_cnt++;

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
        .gpio_num       = pin1,
        .speed_mode     = LEDC_MODE,
        .channel        = (ledc_channel_t)channel,
        .intr_type      = LEDC_INTR_DISABLE,
        .timer_sel      = LEDC_TIMER,
        .duty           = 0, // Set duty to 0%
        .hpoint         = 0,
        .sleep_mode     = LEDC_SLEEP_MODE_NO_ALIVE_NO_PD,
        .flags          = {
            .output_invert = 0,
        },
    };
    ESP_ERROR_CHECK(ledc_channel_config(&ledc_channel));
    return 0;
}

void PWM::set_pwm(uint32_t duty)
{
    ledc_set_duty(LEDC_MODE, (ledc_channel_t)channel, duty);
    ESP_ERROR_CHECK(ledc_update_duty(LEDC_MODE, (ledc_channel_t)channel));
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
    selfTest();
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

void MeterDial::selfTestTimerCallback(TimerHandle_t xTimer)
{
    auto *meter = static_cast<MeterDial *>(pvTimerGetTimerID(xTimer));
    MeterDial::selfTest_ctx_s *st = &meter->selfTestCtx;

    const float accelUp     = 0.2f;  // 上升加速度
    const float accelDown   = 0.2f; // 下降加速度（减速）

    if (st->state == MeterDial::selfTest_ctx_s::ACCEL_UP) {
        // 加速度增加速度
        st->velocity += accelUp;
        st->currentValue += st->velocity;

        if (st->currentValue >= 100) {
            st->currentValue = 100;
            st->velocity *= -1; // 到顶速度反转
            st->state = MeterDial::selfTest_ctx_s::SLOW_DOWN;
        }
        meter->set_percent(st->currentValue);

    } else if (st->state == MeterDial::selfTest_ctx_s::SLOW_DOWN) {
        // 缓慢下降
        st->velocity += accelDown;
        st->currentValue += st->velocity;

        if (st->currentValue <= 8) {
            st->currentValue = 0;
            st->velocity = 0;
            st->state = MeterDial::selfTest_ctx_s::IDLE;
            xTimerStop(st->Timer, 0);
            xTimerDelete(st->Timer, 0);
            st->Timer = nullptr;
        }
        meter->set_percent(st->currentValue);
    }
}

void MeterDial::selfTest()
{
    if (selfTestCtx.Timer != nullptr) {
        xTimerStop(selfTestCtx.Timer, 0);
        xTimerDelete(selfTestCtx.Timer, 0);
    }
    // 创建周期 20ms 的定时器
    selfTestCtx.Timer = xTimerCreate(
                        "SelfTestTimer",
                        pdMS_TO_TICKS(30),
                        pdTRUE,
                        this,
                        &MeterDial::selfTestTimerCallback
                    );
    selfTestCtx.state = MeterDial::selfTest_ctx_s::ACCEL_UP;
    selfTestCtx.currentValue = 0;
    xTimerStart(selfTestCtx.Timer, 0);
}

void MeterDial::waitSelfTestDone()
{
    while (selfTestCtx.state != MeterDial::selfTest_ctx_s::IDLE) {
        vTaskDelay(pdMS_TO_TICKS(30));
    }
}
