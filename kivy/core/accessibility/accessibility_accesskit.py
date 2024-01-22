import kivy
from accesskit import *
from collections import deque
from kivy.uix.behaviors.accessibility import AccessibleBehavior
from sys import platform
from . import AccessibilityBase, Action as KivyAction, Role as KivyRole

class AccessKit(AccessibilityBase):
    def __init__(self, root_window):
        super().__init__()
        self.node_classes = NodeClassSet()
        self.adapter = None
        self.root_window = root_window
        self.root_window_size = None
        root_window.bind(focus=lambda w, v: self._update_root_window_focus(v))
        root_window.bind(size=lambda w, v: self._update_root_window_size(v))
        self.action_request_callback = None
        self.initialized = False

    def _update_root_window_focus(self, is_focused):
        # This is not called the first time the window gets focused, but it really should be.
        if self.adapter is None:
            return
        if platform == 'darwin':
            events = self.adapter.update_view_focus_state(is_focused)
            if events is not None:
                events.raise_events()
        elif 'linux' in platform or 'freebsd' in platform or 'openbsd' in platform:
            self.adapter.update_window_focus_state(is_focused)

    def _update_root_window_size(self, size):
        self.root_window_size = size

    def _build_tree_info(self):
        tree = Tree(self.root_window.uid)
        tree.toolkit_name = "Kivy"
        tree.toolkit_version = kivy.__version__
        return tree

    def _build_dummy_tree(self):
        # If there is no assistive technology running, then this might never be called.
        # We don't really know when the first accessibility tree will be requested: if it's early in the app initialization then we might not have everything ready.
        # It's OK to first push an empty tree update and replace it later.
        root = NodeBuilder(Role.WINDOW).build(self.node_classes)
        update = TreeUpdate(self.root_window.uid)
        update.nodes.append((self.root_window.uid, root))
        update.tree = self._build_tree_info()
        self.initialized = True
        return update

    def _on_action_request(self, request):
        # An assistive technology wants to perform an action on behalf of the user.
        if request.action == Action.FOCUS:
            action = KivyAction.FOCUS
        elif request.action == Action.DEFAULT:
            action = KivyAction.DEFAULT
        else:
            return
        if self.action_request_callback:
            # If we are properly initialized, forward the action to the accessibility manager.
            self.action_request_callback(request.target, action)

    def install(self, window_info, width, height):
        self.root_window_size = (width, height)
        if platform == 'darwin':
            # The following function will need to be called. Since it's SDL2 specific, should it really belong here?
            # macos.add_focus_forwarder_to_window_class("SDLWindow")
            self.adapter = macos.SubclassingAdapter(window_info.window, self._build_dummy_tree, self._on_action_request)
        elif 'linux' in platform or 'freebsd' in platform or 'openbsd' in platform:
            self.adapter = unix.Adapter(self._build_dummy_tree, self._on_action_request)
        elif platform in ('win32', 'cygwin'):
            self.adapter = windows.SubclassingAdapter(window_info.window, self._build_dummy_tree, self._on_action_request)
        # Assume the window has the focus at this time, even though it's probably not true.
        self._update_root_window_focus(True)

    def _build_node(self, accessible):
        builder = NodeBuilder(to_accesskit_role(accessible.accessible_role))
        (x, y) = accessible.accessible_pos
        # On Windows, Y coordinates seem to be reversed, this will be annoying once the window is resized as we'll need to recompute every widget's bounds.
        # Is there a more direct way?
        y = self.root_window_size[1] - y
        (width, height) = accessible.accessible_size
        bounds = Rect(x, y - height, x + width, y)
        builder.set_bounds(bounds)
        
        if accessible.accessible_checked_state is not None:
            builder.set_checked(Checked.TRUE if accessible.accessible_checked_state else Checked.FALSE)
        if accessible.accessible_children:
            for child in accessible.accessible_children[:]:
                builder.push_child(child.accessible_uid)
        if accessible.accessible_name:
            builder.set_name(accessible.accessible_name)
        if accessible.is_focusable:
            builder.add_action(Action.FOCUS)
        if accessible.accessible_checked_state == True:
            builder.add_action(Action.DEFAULT)
            builder.set_default_action_verb(DefaultActionVerb.UNCHECK)
        elif accessible.accessible_checked_state == False:
            builder.add_action(Action.DEFAULT)
            builder.set_default_action_verb(DefaultActionVerb.CHECK)
        elif accessible.is_clickable:
            builder.add_action(Action.DEFAULT)
            builder.set_default_action_verb(DefaultActionVerb.CLICK)
        return builder.build(self.node_classes)

    def _build_tree_update(self, root_window_changed=True):
        # If no widget has the focus, then we must put it on the root window.
        focus = AccessibleBehavior.focused_widget.accessible_uid if AccessibleBehavior.focused_widget else self.root_window_uid
        update = TreeUpdate(focus)
        if root_window_changed:
            builder = NodeBuilder(Role.WINDOW)
            for child in self.root_window.children[:]:
                builder.push_child(child.accessible_uid)
            builder.set_name(self.root_window.title)
            node = builder.build(self.node_classes)
            update.nodes.append((self.root_window.uid, node))
        for (id, accessible) in AccessibleBehavior.updated_widgets.items():
            update.nodes.append((id, self._build_node(accessible)))
        return update

    def update(self, root_window_changed=False):
        if not self.adapter or not self.initialized:
            return False
        events = self.adapter.update_if_active(lambda: self._build_tree_update(root_window_changed))
        if events:
            events.raise_events()
        return True

def to_accesskit_role(role):
    if role == KivyRole.STATIC_TEXT:
        return Role.STATIC_TEXT
    elif role == KivyRole.GENERIC_CONTAINER:
        return Role.GENERIC_CONTAINER
    elif role == KivyRole.CHECK_BOX:
        return Role.CHECK_BOX
    elif role == KivyRole.BUTTON:
        return Role.BUTTON
    return Role.UNKNOWN
