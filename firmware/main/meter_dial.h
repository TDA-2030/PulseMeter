/*
   This example code is in the Public Domain (or CC0 licensed, at your option.)

   Unless required by applicable law or agreed to in writing, this
   software is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
   CONDITIONS OF ANY KIND, either express or implied.
*/
#pragma once
#include <stdint.h>
#include "setting.h"


class PWM {
public:
    PWM() = default;
    ~PWM() = default;

    // 初始化PWM
    bool init(int pin1);

    // 设置PWM占空比
    void set_pwm(uint32_t duty);
private:
    int mot_id;
};


class MeterDial {
public:
    MeterDial(const char *name);

    // 禁止拷贝构造和赋值操作
    MeterDial(const MeterDial &) = delete;
    MeterDial &operator=(const MeterDial &) = delete;

    void init(int pwm_pin);

    void enable(bool is_enable);
    void set_percent(int percent);

    float get_percent()
    {
        return 0;
    }

    float get_max_speed()
    {
        return 0;
    }
    
    void set_max_duty(uint32_t max_duty)
    {
        this->max_duty = max_duty;
    }
    

private:
    const char *name;
    PWM *pwm;
    uint32_t max_duty;

};

#ifdef __cplusplus
extern "C" {
#endif


#ifdef __cplusplus
}
#endif
