# Chapter 12 - FAQ

Q: Is Rust faster than Python for this system?
A: It depends. The system is often I/O bound. Rust helps most when CPU parsing is
   the bottleneck or when latency tail must be reduced.

Q: Why is a batch timing out?
A: The symbols might be illiquid or suspended. Increase message timeout or reduce
   batch size.
