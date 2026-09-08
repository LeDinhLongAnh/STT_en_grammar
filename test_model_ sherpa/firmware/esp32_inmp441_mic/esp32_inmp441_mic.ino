#include <Arduino.h>
#include <driver/i2s.h>

// --- CAU HINH GPIO CHO I2S (ESP32-S3 + INMP441) ---
#define I2S_WS   16   // L/R CLK
#define I2S_SD   6    // Serial Data Out tu mic
#define I2S_SCK  15   // BCLK
#define I2S_PORT I2S_NUM_0

// --- CAU HINH AUDIO ---
#define SAMPLE_RATE 16000
#define CHUNK_SIZE  512 // 512 samples moi frame (32ms audio)

// INMP441 la mic 24-bit chay tren khung 32-bit slot
int32_t rawBuffer[CHUNK_SIZE];
int16_t pcmBuffer[CHUNK_SIZE];

// --- FRAME PROTOCOL CHO PYTHON ---
const uint8_t MAGIC_1 = 0xAA;
const uint8_t MAGIC_2 = 0xBB;

void setup() {
  Serial.begin(2000000);
  delay(1000); // Cho USB CDC khoi tao on dinh
  
  Serial.println("\n==========================================");
  Serial.println("[ESP32-S3] Bat dau khoi tao I2S cho INMP441...");
  
  // INMP441 yeu cau 32-bit slot de lay du 24-bit du lieu
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT, // INMP441 L/R noi GND -> Left
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = CHUNK_SIZE,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  if (err != ESP_OK) {
    Serial.printf("[LOI] i2s_driver_install that bai: %d\n", err);
    return;
  }

  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK,
    .ws_io_num = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD
  };
  
  err = i2s_set_pin(I2S_PORT, &pin_config);
  if (err != ESP_OK) {
    Serial.printf("[LOI] i2s_set_pin that bai: %d\n", err);
    return;
  }

  err = i2s_start(I2S_PORT);
  if (err != ESP_OK) {
    Serial.printf("[LOI] i2s_start that bai: %d\n", err);
    return;
  }

  Serial.println("[ESP32-S3] I2S INMP441 da san sang!");
  Serial.println("[ESP32-S3] Dang truyen stream PCM sang PC...");
  Serial.println("==========================================\n");
}

void loop() {
  size_t bytesIn = 0;
  // Doc du lieu 32-bit tu INMP441
  esp_err_t result = i2s_read(I2S_PORT, rawBuffer, sizeof(rawBuffer), &bytesIn, portMAX_DELAY);

  if (result == ESP_OK && bytesIn > 0) {
    int samplesRead = bytesIn / sizeof(int32_t);
    
    // Convert 24-bit audio trong 32-bit word sang standard 16-bit PCM
    // INMP441 data nam o cac bit cao, dich phai 14 bit (tang gain chut) hoac 16 bit
    for (int i = 0; i < samplesRead; i++) {
      pcmBuffer[i] = (int16_t)(rawBuffer[i] >> 14);
    }

    uint16_t pcmBytes = samplesRead * sizeof(int16_t);
    uint8_t* pcmPtr = (uint8_t*)pcmBuffer;

    // Tinh XOR Checksum
    uint8_t checksum = 0;
    for (size_t i = 0; i < pcmBytes; i++) {
      checksum ^= pcmPtr[i];
    }

    // Gui Frame Protocol: [0xAA, 0xBB] + [Length (2 bytes)] + [PCM] + [Checksum (1 byte)]
    Serial.write(MAGIC_1);
    Serial.write(MAGIC_2);
    Serial.write((uint8_t)(pcmBytes & 0xFF));
    Serial.write((uint8_t)((pcmBytes >> 8) & 0xFF));
    Serial.write(pcmPtr, pcmBytes);
    Serial.write(checksum);
  }
}
