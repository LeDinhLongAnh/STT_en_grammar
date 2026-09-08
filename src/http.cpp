#include "vcc/http.h"

#include <algorithm>
#include <atomic>
#include <condition_variable>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <thread>

#ifdef _WIN32
// clang-format off
#include <winsock2.h>
#include <ws2tcpip.h>
// clang-format on
using socket_t = SOCKET;
using socklen_t = int;
#define VCC_INVALID_SOCKET INVALID_SOCKET
#define VCC_CLOSE_SOCKET closesocket
#else
#include <arpa/inet.h>
#include <csignal>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <signal.h>
#include <sys/socket.h>
#include <unistd.h>
using socket_t = int;
#define VCC_INVALID_SOCKET (-1)
#define VCC_CLOSE_SOCKET ::close
#endif

#include "vcc/core.h"
#include "vcc/log.h"

namespace vcc {
namespace {

struct RouteKey {
  std::string method;
  std::string path;
  bool operator<(const RouteKey &o) const {
    if (method != o.method) return method < o.method;
    return path < o.path;
  }
};

bool SendAll(socket_t fd, const char *data, size_t n) {
  size_t sent = 0;
  while (sent < n) {
    const int chunk = static_cast<int>(std::min<size_t>(n - sent, 1 << 16));
#ifdef _WIN32
    const int w = send(fd, data + sent, chunk, 0);
#else
    const int w = static_cast<int>(send(fd, data + sent, chunk, MSG_NOSIGNAL));
#endif
    if (w <= 0) return false;
    sent += static_cast<size_t>(w);
  }
  return true;
}

const char *StatusText(int code) {
  switch (code) {
    case 200: return "OK";
    case 201: return "Created";
    case 204: return "No Content";
    case 400: return "Bad Request";
    case 403: return "Forbidden";
    case 404: return "Not Found";
    case 405: return "Method Not Allowed";
    case 409: return "Conflict";
    case 413: return "Payload Too Large";
    case 500: return "Internal Server Error";
    case 503: return "Service Unavailable";
    default:  return "OK";
  }
}

}  // namespace

std::string UrlDecode(const std::string &s, bool plus_is_space) {
  std::string out;
  out.reserve(s.size());
  for (size_t i = 0; i < s.size(); ++i) {
    if (s[i] == '%' && i + 2 < s.size()) {
      const std::string hex = s.substr(i + 1, 2);
      char *end = nullptr;
      const long v = std::strtol(hex.c_str(), &end, 16);
      if (end && *end == '\0') {
        out.push_back(static_cast<char>(v));
        i += 2;
        continue;
      }
    }
    out.push_back(plus_is_space && s[i] == '+' ? ' ' : s[i]);
  }
  return out;
}

std::string GuessContentType(const std::string &path) {
  const std::string low = ToLower(path);
  if (EndsWith(low, ".html") || EndsWith(low, ".htm")) return "text/html; charset=utf-8";
  if (EndsWith(low, ".js"))   return "application/javascript; charset=utf-8";
  if (EndsWith(low, ".css"))  return "text/css; charset=utf-8";
  if (EndsWith(low, ".json")) return "application/json; charset=utf-8";
  if (EndsWith(low, ".svg"))  return "image/svg+xml";
  if (EndsWith(low, ".png"))  return "image/png";
  if (EndsWith(low, ".ico"))  return "image/x-icon";
  if (EndsWith(low, ".wav"))  return "audio/wav";
  if (EndsWith(low, ".txt"))  return "text/plain; charset=utf-8";
  return "application/octet-stream";
}

std::string HttpRequest::Param(const std::string &k, const std::string &def) const {
  const auto it = params.find(k);
  return it == params.end() ? def : it->second;
}

std::string HttpRequest::Header(const std::string &k, const std::string &def) const {
  const auto it = headers.find(ToLower(k));
  return it == headers.end() ? def : it->second;
}

HttpResponse HttpResponse::Json(const std::string &json, int status) {
  HttpResponse r;
  r.status = status;
  r.content_type = "application/json; charset=utf-8";
  r.body = json;
  return r;
}

HttpResponse HttpResponse::Text(const std::string &text, int status) {
  HttpResponse r;
  r.status = status;
  r.content_type = "text/plain; charset=utf-8";
  r.body = text;
  return r;
}

HttpResponse HttpResponse::Error(int status, const std::string &message) {
  HttpResponse r;
  r.status = status;
  r.content_type = "application/json; charset=utf-8";
  std::string escaped;
  for (char c : message) {
    if (c == '"' || c == '\\') escaped.push_back('\\');
    if (c == '\n') { escaped += "\\n"; continue; }
    escaped.push_back(c);
  }
  r.body = "{\"error\":\"" + escaped + "\"}";
  return r;
}

struct HttpServer::Impl {
  std::map<RouteKey, Handler> routes;
  std::map<std::string, SseHandler> sse_routes;
  std::vector<std::pair<std::string, std::string>> statics;  // prefix -> dir
  Handler fallback;

  socket_t listen_fd = VCC_INVALID_SOCKET;
  std::atomic<bool> running {false};
  std::thread accept_thread;
  std::atomic<int> live_workers {0};
  int port = 0;
  size_t max_body = 32u * 1024u * 1024u;

  std::mutex wait_mu;
  std::condition_variable wait_cv;

#ifdef _WIN32
  bool wsa_started = false;
#endif

  ~Impl() {
#ifdef _WIN32
    if (wsa_started) WSACleanup();
#endif
  }
};

HttpServer::HttpServer() : impl_(new Impl()) {}
HttpServer::~HttpServer() { Stop(); }

void HttpServer::Route(const std::string &method, const std::string &path, Handler h) {
  impl_->routes[RouteKey {ToUpper(method), path}] = std::move(h);
}

void HttpServer::RouteSse(const std::string &path, SseHandler h) {
  impl_->sse_routes[path] = std::move(h);
}

void HttpServer::ServeStatic(const std::string &prefix, const std::string &dir) {
  impl_->statics.emplace_back(prefix, dir);
}

void HttpServer::SetFallback(Handler h) { impl_->fallback = std::move(h); }

bool HttpServer::running() const { return impl_->running; }
int HttpServer::port() const { return impl_->port; }

namespace {

// Reads until the header terminator, then the declared body length.
bool ReadRequest(socket_t fd, size_t max_body, HttpRequest *req, int *error_status) {
  std::string buf;
  char tmp[8192];
  size_t header_end = std::string::npos;

  while (header_end == std::string::npos) {
    const int n = recv(fd, tmp, sizeof(tmp), 0);
    if (n <= 0) return false;
    buf.append(tmp, static_cast<size_t>(n));
    header_end = buf.find("\r\n\r\n");
    if (header_end == std::string::npos && buf.size() > 64 * 1024) {
      *error_status = 400;
      return false;
    }
  }

  const std::string head = buf.substr(0, header_end);
  const std::vector<std::string> lines = Split(head, '\n');
  if (lines.empty()) {
    *error_status = 400;
    return false;
  }

  const std::vector<std::string> start = SplitWhitespace(lines[0]);
  if (start.size() < 2) {
    *error_status = 400;
    return false;
  }
  req->method = ToUpper(start[0]);
  std::string target = start[1];
  const size_t qm = target.find('?');
  if (qm != std::string::npos) {
    req->query = target.substr(qm + 1);
    target = target.substr(0, qm);
  }
  req->path = UrlDecode(target, /*plus_is_space=*/false);

  for (const std::string &pair : Split(req->query, '&', true)) {
    const size_t eq = pair.find('=');
    if (eq == std::string::npos) {
      req->params[UrlDecode(pair, true)] = "";
    } else {
      req->params[UrlDecode(pair.substr(0, eq), true)] =
          UrlDecode(pair.substr(eq + 1), true);
    }
  }

  for (size_t i = 1; i < lines.size(); ++i) {
    const std::string line = Trim(lines[i]);
    const size_t colon = line.find(':');
    if (colon == std::string::npos) continue;
    req->headers[ToLower(Trim(line.substr(0, colon)))] = Trim(line.substr(colon + 1));
  }

  size_t content_length = 0;
  const std::string cl = req->Header("content-length");
  if (!cl.empty()) {
    int v = 0;
    if (ParseInt(cl, &v) && v > 0) content_length = static_cast<size_t>(v);
  }
  if (content_length > max_body) {
    *error_status = 413;
    return false;
  }

  req->body = buf.substr(header_end + 4);
  while (req->body.size() < content_length) {
    const int n = recv(fd, tmp, sizeof(tmp), 0);
    if (n <= 0) break;
    req->body.append(tmp, static_cast<size_t>(n));
  }
  if (req->body.size() > content_length) req->body.resize(content_length);
  return true;
}

bool WriteResponse(socket_t fd, const HttpResponse &res) {
  std::string head = "HTTP/1.1 " + std::to_string(res.status) + " " +
                     StatusText(res.status) + "\r\n";
  head += "Content-Type: " + res.content_type + "\r\n";
  head += "Content-Length: " + std::to_string(res.body.size()) + "\r\n";
  head += "Connection: close\r\n";
  // The dashboard is a local tool; cached JSON would be actively confusing.
  head += "Cache-Control: no-store\r\n";
  for (const auto &h : res.extra_headers) {
    head += h.first + ": " + h.second + "\r\n";
  }
  head += "\r\n";
  if (!SendAll(fd, head.data(), head.size())) return false;
  if (res.body.empty()) return true;
  return SendAll(fd, res.body.data(), res.body.size());
}

}  // namespace

bool HttpServer::Start(const std::string &host, int port, std::string *error) {
  auto fail = [&](const std::string &m) {
    if (error) *error = m;
    return false;
  };
  if (impl_->running) return fail("server already running");

#ifdef _WIN32
  WSADATA wsa;
  if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) return fail("WSAStartup failed");
  impl_->wsa_started = true;
#else
  // A client that closes early must not kill the process.
  signal(SIGPIPE, SIG_IGN);
#endif

  impl_->max_body = max_body_bytes_;

  socket_t fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (fd == VCC_INVALID_SOCKET) return fail("socket() failed");

  int yes = 1;
  setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<const char *>(&yes),
             sizeof(yes));

  sockaddr_in addr;
  std::memset(&addr, 0, sizeof(addr));
  addr.sin_family = AF_INET;
  addr.sin_port = htons(static_cast<unsigned short>(port));
  const std::string bind_host = host.empty() ? "127.0.0.1" : host;
  if (inet_pton(AF_INET, bind_host.c_str(), &addr.sin_addr) != 1) {
    VCC_CLOSE_SOCKET(fd);
    return fail("not an IPv4 address: " + bind_host);
  }
  if (bind_host != "127.0.0.1" && bind_host != "localhost") {
    VCC_WARN << "binding to " << bind_host
             << ": this server has no authentication, anyone who can reach the "
                "port can drive the recogniser";
  }

  if (bind(fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) != 0) {
    VCC_CLOSE_SOCKET(fd);
    return fail("cannot bind " + bind_host + ":" + std::to_string(port) +
                " (already in use?)");
  }
  if (listen(fd, 32) != 0) {
    VCC_CLOSE_SOCKET(fd);
    return fail("listen() failed");
  }

  impl_->listen_fd = fd;
  impl_->port = port;
  impl_->running = true;

  impl_->accept_thread = std::thread([this] {
    while (impl_->running) {
      sockaddr_in peer;
      socklen_t plen = sizeof(peer);
      socket_t cfd = accept(impl_->listen_fd, reinterpret_cast<sockaddr *>(&peer), &plen);
      if (cfd == VCC_INVALID_SOCKET) {
        if (!impl_->running) break;
        continue;
      }
      ++impl_->live_workers;
      std::thread worker([this, cfd] {
        struct Leave {
          Impl *impl;
          socket_t fd;
          ~Leave() {
            VCC_CLOSE_SOCKET(fd);
            --impl->live_workers;
          }
        } leave {impl_.get(), cfd};

        HttpRequest req;
        int err_status = 400;
        if (!ReadRequest(cfd, impl_->max_body, &req, &err_status)) {
          WriteResponse(cfd, HttpResponse::Error(err_status, "malformed request"));
          return;
        }

        // 1. server-sent events
        const auto sse = impl_->sse_routes.find(req.path);
        if (sse != impl_->sse_routes.end() && req.method == "GET") {
          std::string head =
              "HTTP/1.1 200 OK\r\n"
              "Content-Type: text/event-stream\r\n"
              "Cache-Control: no-store\r\n"
              "Connection: close\r\n\r\n";
          if (SendAll(cfd, head.data(), head.size())) {
            sse->second(req, [cfd](const std::string &event, const std::string &data) {
              std::string frame;
              if (!event.empty()) frame += "event: " + event + "\n";
              // SSE data must not contain bare newlines
              for (const std::string &line : Split(data, '\n')) {
                frame += "data: " + line + "\n";
              }
              frame += "\n";
              return SendAll(cfd, frame.data(), frame.size());
            });
          }
          return;
        }

        // 2. exact route
        const auto route = impl_->routes.find(RouteKey {req.method, req.path});
        if (route != impl_->routes.end()) {
          HttpResponse res;
          try {
            res = route->second(req);
          } catch (const std::exception &e) {
            res = HttpResponse::Error(500, std::string("handler threw: ") + e.what());
          }
          WriteResponse(cfd, res);
          return;
        }

        // 3. static files
        for (const auto &st : impl_->statics) {
          if (!StartsWith(req.path, st.first)) continue;
          std::string rel = req.path.substr(st.first.size());
          if (rel.empty() || rel == "/") rel = "index.html";
          if (rel.front() == '/') rel = rel.substr(1);
          if (rel.find("..") != std::string::npos) {
            WriteResponse(cfd, HttpResponse::Error(403, "path traversal rejected"));
            return;
          }
          const std::string full = PathJoin(st.second, rel);
          std::string data;
          if (ReadFile(full, &data)) {
            HttpResponse res;
            res.content_type = GuessContentType(full);
            res.body = std::move(data);
            WriteResponse(cfd, res);
            return;
          }
        }

        // 4. fallback
        HttpResponse res = impl_->fallback
                               ? impl_->fallback(req)
                               : HttpResponse::Error(404, "no route for " + req.path);
        WriteResponse(cfd, res);
      });
      // Detached: each connection is short-lived and self-contained, and the
      // counter is only there so Stop() can log stragglers.
      worker.detach();
    }
  });

  VCC_INFO << "http server listening on http://" << bind_host << ":" << port;
  return true;
}

void HttpServer::Stop() {
  if (!impl_ || !impl_->running) return;
  impl_->running = false;
  if (impl_->listen_fd != VCC_INVALID_SOCKET) {
#ifdef _WIN32
    shutdown(impl_->listen_fd, SD_BOTH);
#else
    shutdown(impl_->listen_fd, SHUT_RDWR);
#endif
    VCC_CLOSE_SOCKET(impl_->listen_fd);
    impl_->listen_fd = VCC_INVALID_SOCKET;
  }
  if (impl_->accept_thread.joinable()) impl_->accept_thread.join();
  impl_->wait_cv.notify_all();
  VCC_INFO << "http server stopped";
}

void HttpServer::Wait() {
  std::unique_lock<std::mutex> lock(impl_->wait_mu);
  impl_->wait_cv.wait(lock, [this] { return !impl_->running.load(); });
}

}  // namespace vcc
