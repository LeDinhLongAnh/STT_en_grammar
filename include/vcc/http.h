// A small blocking HTTP/1.1 server, thread-per-connection.
//
// The dashboard needs to serve a handful of files and answer a handful of JSON
// calls on localhost. That is a job for ~300 lines of sockets, not for an
// embedded web framework -- and the same code cross-compiles for the router,
// where a dependency-free build matters.
//
// Deliberately not supported: TLS, keep-alive pipelining beyond one request in
// flight per connection, chunked request bodies. It binds to 127.0.0.1 by
// default and refuses non-loopback binds unless asked explicitly, because this
// server has no authentication and should not be reachable from the network.
#pragma once

#include <functional>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace vcc {

struct HttpRequest {
  std::string method;
  std::string path;                             // decoded, without query
  std::string query;                            // raw query string
  std::map<std::string, std::string> params;    // decoded query params
  std::map<std::string, std::string> headers;   // header names lowercased
  std::string body;

  std::string Param(const std::string &k, const std::string &def = "") const;
  std::string Header(const std::string &k, const std::string &def = "") const;
};

struct HttpResponse {
  int status = 200;
  std::string content_type = "application/json; charset=utf-8";
  std::string body;
  std::vector<std::pair<std::string, std::string>> extra_headers;

  static HttpResponse Json(const std::string &json, int status = 200);
  static HttpResponse Text(const std::string &text, int status = 200);
  static HttpResponse Error(int status, const std::string &message);
  // Streaming responses (server-sent events) are signalled by this flag; the
  // handler writes to the socket itself through the Streamer it is given.
  bool stream = false;
};

// Handler for a streaming response. Return false from the write callback to
// stop; the server closes the connection afterwards.
using SseWriter = std::function<bool(const std::string &event, const std::string &data)>;

class HttpServer {
 public:
  using Handler = std::function<HttpResponse(const HttpRequest &)>;
  using SseHandler = std::function<void(const HttpRequest &, const SseWriter &)>;

  HttpServer();
  ~HttpServer();
  HttpServer(const HttpServer &) = delete;
  HttpServer &operator=(const HttpServer &) = delete;

  // Exact-path route.
  void Route(const std::string &method, const std::string &path, Handler h);
  // Server-sent-events route.
  void RouteSse(const std::string &path, SseHandler h);
  // Serves files under `dir` for any path starting with `prefix`.
  // Paths containing ".." are rejected.
  void ServeStatic(const std::string &prefix, const std::string &dir);
  // Response for anything unmatched.
  void SetFallback(Handler h);

  // Binds and starts accepting. Returns false if the port is taken.
  // `max_body_bytes` caps request bodies; audio uploads need a few MB.
  bool Start(const std::string &host, int port, std::string *error);
  void Stop();
  bool running() const;
  int port() const;

  void set_max_body_bytes(size_t n) { max_body_bytes_ = n; }

  // Blocks until Stop() is called from another thread or a signal handler.
  void Wait();

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
  size_t max_body_bytes_ = 32u * 1024u * 1024u;
};

// Guesses a Content-Type from a filename extension.
std::string GuessContentType(const std::string &path);

// Percent-decoding, '+' treated as space in query strings.
std::string UrlDecode(const std::string &s, bool plus_is_space);

}  // namespace vcc
