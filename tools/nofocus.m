// 注入 Godot（DYLD_INSERT_LIBRARIES）后让它在后台安静地跑：不激活自己、不抢焦点、不出现在 Dock，
// 窗口完全透明、不接收鼠标、放在所有窗口后面。渲染照常进行，截图、烘焙 GI 不受影响。
// 由 tools/godot_bg.sh 按需编译，不用手动构建。
#import <AppKit/AppKit.h>
#import <objc/runtime.h>

static void swap(Class cls, SEL orig, SEL repl) {
  Method m = class_getInstanceMethod(cls, orig);
  Method r = class_getInstanceMethod(cls, repl);
  if (m && r) method_exchangeImplementations(m, r);
}

static void hide_window(NSWindow *w) {
  w.alphaValue = 0;
  w.ignoresMouseEvents = YES;
  w.hasShadow = NO;
  [w orderBack:nil];
}

@implementation NSApplication (NoFocus)
- (void)nf_activateIgnoringOtherApps:(BOOL)flag {}
- (void)nf_activate {}
- (BOOL)nf_setActivationPolicy:(NSApplicationActivationPolicy)p {
  // Accessory：没有 Dock 图标、不接管菜单栏，但仍然可以有窗口、正常渲染
  return [self nf_setActivationPolicy:NSApplicationActivationPolicyAccessory];
}
- (NSInteger)nf_requestUserAttention:(NSRequestUserAttentionType)t { return 0; }
@end

@implementation NSRunningApplication (NoFocus)
- (BOOL)nf_activateWithOptions:(NSApplicationActivationOptions)o {
  if ([self isEqual:NSRunningApplication.currentApplication]) return NO;
  return [self nf_activateWithOptions:o];
}
@end

@implementation NSWindow (NoFocus)
- (void)nf_makeKeyAndOrderFront:(id)sender { hide_window(self); }
- (void)nf_orderFront:(id)sender { hide_window(self); }
- (void)nf_orderFrontRegardless { hide_window(self); }
- (void)nf_makeKeyWindow {}
- (void)nf_setAlphaValue:(CGFloat)a { [self nf_setAlphaValue:0]; }
@end

__attribute__((constructor)) static void nofocus_init(void) {
  Class app = NSApplication.class, win = NSWindow.class;
  swap(app, @selector(activateIgnoringOtherApps:), @selector(nf_activateIgnoringOtherApps:));
  swap(app, @selector(activate), @selector(nf_activate));
  swap(app, @selector(setActivationPolicy:), @selector(nf_setActivationPolicy:));
  swap(app, @selector(requestUserAttention:), @selector(nf_requestUserAttention:));
  swap(NSRunningApplication.class, @selector(activateWithOptions:), @selector(nf_activateWithOptions:));
  swap(win, @selector(makeKeyAndOrderFront:), @selector(nf_makeKeyAndOrderFront:));
  swap(win, @selector(orderFront:), @selector(nf_orderFront:));
  swap(win, @selector(orderFrontRegardless), @selector(nf_orderFrontRegardless));
  swap(win, @selector(makeKeyWindow), @selector(nf_makeKeyWindow));
  swap(win, @selector(setAlphaValue:), @selector(nf_setAlphaValue:));
}
