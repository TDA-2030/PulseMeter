/* HTTP Restful API Server

   This example code is in the Public Domain (or CC0 licensed, at your option.)

   Unless required by applicable law or agreed to in writing, this
   software is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
   CONDITIONS OF ANY KIND, either express or implied.
*/
#include <string.h>
#include <fcntl.h>
#include "esp_http_server.h"
#include "esp_chip_info.h"
#include "esp_random.h"
#include "esp_log.h"
#include "esp_vfs.h"
#include "cJSON.h"
#include "rest_server.h"
#include "setting.h"
#include "adc.h"

static const char *REST_TAG = "esp-rest";
#define REST_CHECK(a, str, goto_tag, ...)                                              \
    do                                                                                 \
    {                                                                                  \
        if (!(a))                                                                      \
        {                                                                              \
            ESP_LOGE(REST_TAG, "%s(%d): " str, __FUNCTION__, __LINE__, ##__VA_ARGS__); \
            goto goto_tag;                                                             \
        }                                                                              \
    } while (0)

#define FILE_PATH_MAX (ESP_VFS_PATH_MAX + 128)
#define SCRATCH_BUFSIZE (1024*20)

typedef struct rest_server_context {
    char base_path[ESP_VFS_PATH_MAX + 1];
    char scratch[SCRATCH_BUFSIZE];
} rest_server_context_t;

#define CHECK_FILE_EXTENSION(filename, ext) (strcasecmp(&filename[strlen(filename) - strlen(ext)], ext) == 0)

/* Set HTTP response content type according to file extension */
static esp_err_t set_content_type_from_file(httpd_req_t *req, const char *filepath)
{
    const char *type = "text/plain";
    if (CHECK_FILE_EXTENSION(filepath, ".html")) {
        type = "text/html";
    } else if (CHECK_FILE_EXTENSION(filepath, ".js")) {
        type = "application/javascript";
    } else if (CHECK_FILE_EXTENSION(filepath, ".css")) {
        type = "text/css";
    } else if (CHECK_FILE_EXTENSION(filepath, ".png")) {
        type = "image/png";
    } else if (CHECK_FILE_EXTENSION(filepath, ".ico")) {
        type = "image/x-icon";
    } else if (CHECK_FILE_EXTENSION(filepath, ".svg")) {
        type = "text/xml";
    }
    return httpd_resp_set_type(req, type);
}

/* Send HTTP response with the contents of the requested file */
static esp_err_t rest_common_get_handler(httpd_req_t *req)
{
    char filepath[FILE_PATH_MAX];

    rest_server_context_t *rest_context = (rest_server_context_t *)req->user_ctx;
    strlcpy(filepath, rest_context->base_path, sizeof(filepath));
    if (req->uri[strlen(req->uri) - 1] == '/') {
        strlcat(filepath, "/index.html", sizeof(filepath));
    } else {
        strlcat(filepath, req->uri, sizeof(filepath));
    }
    int fd = open(filepath, O_RDONLY, 0);
    if (fd == -1) {
        ESP_LOGE(REST_TAG, "Failed to open file : %s", filepath);
        /* Respond with 500 Internal Server Error */
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Failed to read existing file");
        return ESP_FAIL;
    }

    set_content_type_from_file(req, filepath);

    char *chunk = rest_context->scratch;
    ssize_t read_bytes;
    do {
        /* Read file in chunks into the scratch buffer */
        read_bytes = read(fd, chunk, SCRATCH_BUFSIZE);
        if (read_bytes == -1) {
            ESP_LOGE(REST_TAG, "Failed to read file : %s", filepath);
        } else if (read_bytes > 0) {
            /* Send the buffer contents as HTTP response chunk */
            if (httpd_resp_send_chunk(req, chunk, read_bytes) != ESP_OK) {
                close(fd);
                ESP_LOGE(REST_TAG, "File sending failed!");
                /* Abort sending file */
                httpd_resp_sendstr_chunk(req, NULL);
                /* Respond with 500 Internal Server Error */
                httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Failed to send file");
                return ESP_FAIL;
            }
        }
    } while (read_bytes > 0);
    /* Close file after sending complete */
    close(fd);
    ESP_LOGI(REST_TAG, "File %s sending complete", filepath);
    /* Respond with an empty chunk to signal HTTP response completion */
    httpd_resp_send_chunk(req, NULL, 0);
    return ESP_OK;
}

static void cjson_add_num_as_str(cJSON *obj, const char *name, double number)
{
    char buffer[10];
    snprintf(buffer, sizeof(buffer), "%.2f", number);  // 保留 2 位小数
    cJSON_AddStringToObject(obj, name, buffer);
}

static double cjson_get_num(cJSON *obj, const char *name)
{
    cJSON *item = cJSON_GetObjectItem(obj, name);
    if (!item) {
        ESP_LOGE(REST_TAG, "Error: %s not found in JSON", name);
        return 0.0;
    }

    if (!cJSON_IsNumber(item)) {
        ESP_LOGE(REST_TAG, "Error: %s is not a number", name);
        return 0.0;
    }
    return item->valuedouble;
}

/* json format of setting */
/*
{
    pid:{
        pos:{
            p:0.1,
            i:0.1,
            d:0.1,
            maxout:200,
            maxitg:200,
        },
        vel:{
            p:0.1,
            i:0.1,
            d:0.1,
            maxout:200,
            maxitg:200,
        },
        pitch:{
            p:0.1,
            i:0.1,
            d:0.1,
            maxout:200,
            maxitg:200,
        },
    },
    mode:"auto",
    th:{
        maxv:12.1,
        minv:10.1,
    },
    man:{
        pitch:20,
        yaw:30,
    },
}
*/

static esp_err_t setting_post_handler(httpd_req_t *req)
{
    int total_len = req->content_len;
    int cur_len = 0;
    char *buf = ((rest_server_context_t *)(req->user_ctx))->scratch;
    int received = 0;
    if (total_len >= SCRATCH_BUFSIZE) {
        /* Respond with 500 Internal Server Error */
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "content too long");
        return ESP_FAIL;
    }
    while (cur_len < total_len) {
        received = httpd_req_recv(req, buf + cur_len, total_len);
        if (received <= 0) {
            /* Respond with 500 Internal Server Error */
            httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Failed to post control value");
            return ESP_FAIL;
        }
        cur_len += received;
    }
    buf[total_len] = '\0';

    cJSON *root = cJSON_Parse(buf);
    if (!root) {
        printf("Error parsing JSON!\n");
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Error parsing JSON!");
        return ESP_FAIL;
    }
    printf("Received JSON: %s\n", buf);
    

    cJSON_Delete(root);
    httpd_resp_sendstr(req, "Post control value successfully");
    g_settings.save();
    return ESP_OK;
}

static esp_err_t setting_get_handler(httpd_req_t *req)
{
    httpd_resp_set_type(req, "application/json");

    // 创建根对象
    cJSON *root = cJSON_CreateObject();

    // 创建 pid 对象
    cJSON *pid = cJSON_CreateObject();
    cJSON *pos = cJSON_CreateObject();
    cJSON *vel = cJSON_CreateObject();

   

    // 组装 pid
    cJSON_AddItemToObject(pid, "pos", pos);
    cJSON_AddItemToObject(pid, "vel", vel);


    // 创建 man 对象
    cJSON *man = cJSON_CreateObject();
    cJSON_AddItemToObject(root, "man", man);

    // 打印 JSON 字符串
    char *json_string = cJSON_PrintUnformatted(root);
    printf("%s\n", json_string);

    httpd_resp_sendstr(req, json_string);

    // 释放内存
    free((void *)json_string);
    cJSON_Delete(root);
    return ESP_OK;
}

static esp_err_t sysctrl_post_handler(httpd_req_t *req)
{
    int total_len = req->content_len;
    int cur_len = 0;
    char *buf = ((rest_server_context_t *)(req->user_ctx))->scratch;
    int received = 0;
    if (total_len >= SCRATCH_BUFSIZE) {
        /* Respond with 500 Internal Server Error */
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "content too long");
        return ESP_FAIL;
    }
    while (cur_len < total_len) {
        received = httpd_req_recv(req, buf + cur_len, total_len);
        if (received <= 0) {
            /* Respond with 500 Internal Server Error */
            httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Failed to post control value");
            return ESP_FAIL;
        }
        cur_len += received;
    }
    buf[total_len] = '\0';

    cJSON *root = cJSON_Parse(buf);
    if (!root) {
        printf("Error parsing JSON!\n");
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Error parsing JSON!");
        return ESP_FAIL;
    }
    printf("Received JSON: %s\n", buf);
    // 解析 restart
    cJSON *restart = cJSON_GetObjectItem(root, "restart");
    if (restart) {
        if (restart->valueint == 1) {
            printf("Restarting...\n");
            esp_restart();
        }
    }

    cJSON_Delete(root);
    httpd_resp_sendstr(req, "Post control value successfully");
    return ESP_OK;
}

/* Simple handler for getting system handler */
static esp_err_t system_info_get_handler(httpd_req_t *req)
{
    httpd_resp_set_type(req, "application/json");
    cJSON *root = cJSON_CreateObject();
    esp_chip_info_t chip_info;
    esp_chip_info(&chip_info);
    cJSON_AddStringToObject(root, "idfversion", IDF_VER);
    cJSON_AddStringToObject(root, "chip", CONFIG_IDF_TARGET);
    cJSON_AddNumberToObject(root, "cores", chip_info.cores);
    cJSON_AddStringToObject(root, "compile date", __DATE__);
    cJSON_AddStringToObject(root, "compile time", __TIME__);
    const char *sys_info = cJSON_PrintUnformatted(root);
    httpd_resp_sendstr(req, sys_info);
    free((void *)sys_info);
    cJSON_Delete(root);
    return ESP_OK;
}


WebServer::WebServer(const char *base_path)
{
    this->base_path = base_path;
}

WebServer::~WebServer()
{

}

esp_err_t WebServer::on(const char *url, httpd_method_t method, httpd_uri_handler_t handler, void *user_ctx)
{
    httpd_uri_t _uri = {
        .uri = url,
        .method = method,
        .handler = handler,
        .user_ctx = user_ctx,
    };
    return httpd_register_uri_handler(server, &_uri);
}

esp_err_t WebServer::start()
{
    rest_server_context_t *rest_context = NULL;
    httpd_config_t config;

    REST_CHECK(base_path, "wrong base path", err);

    rest_context = (rest_server_context_t *)calloc(1, sizeof(rest_server_context_t));
    REST_CHECK(rest_context, "No memory for rest context", err);
    strlcpy(rest_context->base_path, base_path, sizeof(rest_context->base_path));

    config = HTTPD_DEFAULT_CONFIG();
    config.uri_match_fn = httpd_uri_match_wildcard;

    ESP_LOGI(REST_TAG, "Starting HTTP Server");
    REST_CHECK(httpd_start(&server, &config) == ESP_OK, "Start server failed", err_start);

    on("/api/v1/sysinfo", HTTP_GET, system_info_get_handler, rest_context);
    on("/api/v1/setting", HTTP_GET, setting_get_handler, rest_context);
    on("/api/v1/setting", HTTP_POST, setting_post_handler, rest_context);
    on("/api/v1/sysctrl", HTTP_POST, sysctrl_post_handler, rest_context);
    on("/*", HTTP_GET, rest_common_get_handler, rest_context);

    return ESP_OK;
err_start:
    free(rest_context);
err:
    return ESP_FAIL;
}


esp_err_t WebServer::stop()
{
    ESP_LOGW(REST_TAG, "Stopping HTTP Server");
    return httpd_stop(server);
}
