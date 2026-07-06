#ifndef LIGHT_BELT_STM32_CONFIG_H
#define LIGHT_BELT_STM32_CONFIG_H

#include <Arduino.h>

// NOT HARDWARE VERIFIED. Update per flashed node after bench validation.
static constexpr uint8_t NODE_ID = 1;
static constexpr uint8_t BROADCAST_NODE_ID = 0xFF;

static constexpr uint32_t PWM_PIN_R = PA0;   // TIM2_CH1
static constexpr uint32_t PWM_PIN_G = PA1;   // TIM2_CH2
static constexpr uint32_t PWM_PIN_B = PA2;   // TIM2_CH3
static constexpr uint32_t PWM_PIN_WW = PA3;  // TIM2_CH4
static constexpr uint32_t PWM_PIN_CW = PA6;  // TIM3_CH1

static constexpr uint32_t UART_TX = PA9;
static constexpr uint32_t UART_RX = PA10;

static constexpr uint32_t RS485_BAUDRATE = 115200;
static constexpr uint32_t BYTE_TIMEOUT_MS = 5;
static constexpr uint32_t SAFE_STATE_TIMEOUT_MS = 1000;

#endif
