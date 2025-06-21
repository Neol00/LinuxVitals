#!/usr/bin/env python

# LinuxVitals - System Monitoring and Control Application for Linux
# Copyright (c) 2024 Noel Ejemyr <noelejemyr@protonmail.com>
#
# LinuxVitals is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# LinuxVitals is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, GLib, Gdk

class WidgetFactory:
    def __init__(self, logger, global_state):
        # References to instances
        self.logger = logger
        self.global_state = global_state

        self.scales = []  # Store references to created scales

    def create_window(self, title, transient_for=None, default_width=100, default_height=100):
        # Create a new Gtk.Window
        try:
            window = Gtk.Window()
            window.set_title(title)
            window.set_default_size(default_width, default_height)
            if transient_for:
                window.set_transient_for(transient_for)
            window.set_resizable(False)
            return window
        except Exception as e:
            self.logger.error("Failed to create window: %s", e)
            return None

    def create_box(self, container, x=0, y=0, **kwargs):
        # Create a new Gtk.Box widget with vertical orientation and add it to the container
        try:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            if 'spacing' in kwargs:
                box.set_spacing(kwargs['spacing'])
            if 'hexpand' in kwargs:
                box.set_hexpand(kwargs['hexpand'])
            if 'vexpand' in kwargs:
                box.set_vexpand(kwargs['vexpand'])
            if 'homogeneous' in kwargs:
                box.set_homogeneous(kwargs['homogeneous'])
            self._set_margins(box, **kwargs)
            self._attach_widget(container, box, x, y)
            return box
        except Exception as e:
            self.logger.error("Failed to create box: %s", e)
            return None

    def create_grid(self):
        # Create a new Gtk.Grid widget
        try:
            grid = Gtk.Grid()
            return grid
        except Exception as e:
            self.logger.error("Failed to create grid: %s", e)
            return None

    def create_notebook(self, parent):
        # Create a new Gtk.Notebook widget and add it to the parent container
        try:
            notebook = Gtk.Notebook()
            parent.append(notebook)
            notebook.add_css_class('notebook')
            return notebook
        except Exception as e:
            self.logger.error("Failed to create notebook: %s", e)
            return None

    def create_tab(self, notebook, tab_name):
        # Create a new tab for the Gtk.Notebook widget
        try:
            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled_window.set_hexpand(True)
            scrolled_window.set_vexpand(True)

            tab = Gtk.Box()
            tab.set_orientation(Gtk.Orientation.VERTICAL)
            tab.set_margin_start(10)
            tab.set_margin_end(10)
            tab.set_margin_top(10)
            tab.set_margin_bottom(10)
            scrolled_window.set_child(tab)

            tab_label = Gtk.Label(label=tab_name)
            tab_label.set_angle(0)  # Ensure text is horizontal
            tab_label.add_css_class('tab-label')
            notebook.append_page(scrolled_window, tab_label)
            return tab
        except Exception as e:
            self.logger.error("Failed to create tab: %s", e)
            return None

    def create_settings_tab(self, notebook, settings_tab_name):
        # Create a new settings tab for the Gtk.Notebook widget
        try:
            settings_tab = Gtk.Box()
            settings_tab.set_orientation(Gtk.Orientation.VERTICAL)
            settings_tab_label = Gtk.Label(label=settings_tab_name)
            settings_tab_label.add_css_class('settings-tab-label')
            notebook.append_page(settings_tab, settings_tab_label)
            return settings_tab
        except Exception as e:
            self.logger.error("Failed to create settings tab: %s", e)
            return None

    def create_about_tab(self, notebook, about_tab_name):
        # Create a new about tab for the Gtk.Notebook widget
        try:
            about_tab = Gtk.Box()
            about_tab.set_orientation(Gtk.Orientation.VERTICAL)
            about_tab_label = Gtk.Label(label=about_tab_name)
            about_tab_label.add_css_class('about-tab-label')
            notebook.append_page(about_tab, about_tab_label)
            return about_tab
        except Exception as e:
            self.logger.error("Failed to create about tab: %s", e)
            return None

    def create_label(self, container, text=None, markup=None, x=0, y=0, **kwargs):
        # Create a new Gtk.Label widget and add it to the container
        try:
            label = Gtk.Label()
            if markup:
                label.set_markup(markup)
            else:
                label.set_text(text)

            self._set_margins(label, **kwargs)
            self._attach_widget(container, label, x, y)
            return label
        except Exception as e:
            self.logger.error("Failed to create label: %s", e)
            return None

    def create_entry(self, container, text="N/A", editable=False, width_chars=10, x=0, y=0, **kwargs):
        # Create a new Gtk.Entry widget and add it to the container
        try:
            entry = Gtk.Entry()
            entry.set_text(text)
            entry.set_editable(editable)
            entry.set_width_chars(width_chars)
            entry.set_can_focus(False)  # Disable focus if not editable

            self._set_margins(entry, **kwargs)
            self._attach_widget(container, entry, x, y)
            return entry
        except Exception as e:
            self.logger.error("Failed to create entry: %s", e)
            return None

    def create_scale(self, container, command, from_value, to_value, x=0, y=0, Negative=False, Frequency=False, **kwargs):
        # Create a new Gtk.Scale widget and add it to the container
        try:
            adjustment = Gtk.Adjustment(lower=from_value, upper=to_value, step_increment=1)
            scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
            scale.set_draw_value(False)  # Don't draw the built-in value

            overlay = Gtk.Overlay()
            label = Gtk.Label()

            overlay.set_child(scale)
            overlay.add_overlay(label)

            def update_label(scale, label):
                value = scale.get_value()
                if Frequency:
                    if self.global_state.display_ghz:
                        display_value = value / 1000.0
                        label.set_text(f"{display_value:.2f} GHz")
                    else:
                        label.set_text(f"{value:.0f} MHz")
                else:
                    if Negative:
                        display_value = -value  # Set scale digits to display a negative value
                    else:
                        display_value = value
                    label.set_text(str(int(display_value)))
                self._update_scale_label_position(scale, label)

            def on_scale_value_changed(scale):
                update_label(scale, label)

            if command:
                scale.connect("value-changed", command)
            scale.connect("value-changed", lambda s: on_scale_value_changed(s))
            on_scale_value_changed(scale)

            label.set_halign(Gtk.Align.START)
            label.set_valign(Gtk.Align.CENTER)

            self._set_margins(overlay, **kwargs)
            self._attach_widget(container, overlay, x, y)

            # To manage visibility of both scale and label
            scale.connect("notify::visible", lambda scale, param: overlay.set_visible(scale.get_visible()))

            # Store references to the scale and label for later updates
            self.scales.append((scale, label, Frequency))

            return scale
        except Exception as e:
            self.logger.error(f"Failed to create scale: {e}")
            return None

    def update_all_scale_labels(self):
        # Update the position of all scale labels
        for scale, label, is_frequency in self.scales:
            self._update_scale_label_position(scale, label)

    def _update_scale_label_position(self, scale, label):
        try:
            adjustment = scale.get_adjustment()
            scale_width = scale.get_allocated_width()
            handle_position = (scale.get_value() - adjustment.get_lower()) / (adjustment.get_upper() - adjustment.get_lower())
            handle_x = scale_width * handle_position

            label_width = label.get_allocated_width()
            label_x = handle_x - (label_width / 2)
            label_x = max(min(label_x, scale_width - label_width), 0)

            label.set_margin_start(int(label_x))
            label.set_margin_top(25)  # Position the label below the slider with less margin
        except Exception as e:
            self.logger.error(f"Failed to calculate scales position: {e}")

    def update_frequency_scale_labels(self):
        # Update the labels for all frequency scales
        for scale, label, is_frequency in self.scales:
            if is_frequency:  # Only update if it is a frequency scale
                try:
                    value = scale.get_value()
                    if self.global_state.display_ghz:
                        display_value = value / 1000.0
                        label.set_text(f"{display_value:.2f} GHz")
                    else:
                        label.set_text(f"{value:.0f} MHz")
                    self._update_scale_label_position(scale, label)
                except Exception as e:
                    self.logger.error(f"Error updating label for scale: {e}")

    def create_button(self, container, text, command=None, x=0, y=0, **kwargs):
        # Create a new Gtk.Button widget and add it to the container
        try:
            button = Gtk.Button()
            if command:
                button.connect("clicked", command)
            # Use a label widget for the text inside the button
            label = Gtk.Label(label=text)
            button.set_child(label)
            button.add_css_class('button')

            self._set_margins(button, **kwargs)
            self._attach_widget(container, button, x, y)
            return button
        except Exception as e:
            self.logger.error("Failed to create button: %s", e)
            return None

    def create_info_button(self, container, callback, x=0, y=0, **kwargs):
        # Create a new info button (Gtk.Button) with an information icon and add it to the container
        try:
            button = Gtk.Button()
            button.connect("clicked", callback)

            # Create an image with the icon name
            info_icon = Gtk.Image.new_from_icon_name("dialog-information")
            button.set_child(info_icon)
            button.add_css_class('infobutton')

            self._set_margins(button, **kwargs)
            self._attach_widget(container, button, x, y)
            return button
        except Exception as e:
            self.logger.error("Failed to create info button: %s", e)
            return None

    def create_spinbutton(self, container, value, lower, upper, step_increment, page_increment, climb_rate, digits, command=None, x=0, y=0, **kwargs):
        # Create a new Gtk.SpinButton widget and add it to the container
        try:
            adjustment = Gtk.Adjustment(value=value, lower=lower, upper=upper, step_increment=step_increment, page_increment=page_increment)
            spinbutton = Gtk.SpinButton()
            spinbutton.set_adjustment(adjustment)
            spinbutton.set_climb_rate(climb_rate)
            spinbutton.set_digits(digits)
            if command:
                spinbutton.connect("value-changed", command)

            self._set_margins(spinbutton, **kwargs)
            self._attach_widget(container, spinbutton, x, y)
            return spinbutton
        except Exception as e:
            self.logger.error("Failed to create SpinButton: %s", e)
            return None

    def create_dropdown(self, container, values, command, x=0, y=0, **kwargs):
        try:
            store = Gtk.StringList()
            for val in values:
                store.append(val)
            dropdown = Gtk.DropDown.new(store, None)
            
            # Change the signal connection
            dropdown.connect("notify::selected", command)

            # Apply hexpand and vexpand if provided in kwargs
            if 'hexpand' in kwargs:
                dropdown.set_hexpand(kwargs['hexpand'])
            if 'vexpand' in kwargs:
                dropdown.set_vexpand(kwargs['vexpand'])

            self._set_margins(dropdown, **kwargs)
            self._attach_widget(container, dropdown, x, y)
            return dropdown
        except Exception as e:
            self.logger.error("Failed to create dropdown: %s", e)
            return None

    def create_checkbutton(self, container, text, variable, command=None, x=0, y=0, **kwargs):
        # Create a new Gtk.CheckButton widget and add it to the container
        try:
            checkbutton = Gtk.CheckButton()
            label = Gtk.Label(label=text)
            checkbutton.set_child(label)
            checkbutton.set_active(variable)  # Set the initial state
            if command is not None:
                checkbutton.connect("toggled", command)

            self._set_margins(checkbutton, **kwargs)
            self._attach_widget(container, checkbutton, x, y)
            return checkbutton
        except Exception as e:
            self.logger.error("Failed to create checkbutton: %s", e)
            return None

    def _attach_widget(self, container, widget, x=0, y=0):
        # Attach a widget to the given container
        try:
            if widget.get_parent() is not None:
                self.logger.warning("Widget already has a parent and won't be reattached.")
                return

            if container is None:
                # If container is None, don't attach the widget
                return

            if isinstance(container, Gtk.Dialog):
                content_area = container.get_content_area()
                content_area.append(widget)
            elif isinstance(container, Gtk.Grid):
                # Use the provided x,y coordinates for Grid positioning
                container.attach(widget, x, y, 1, 1)
            elif isinstance(container, Gtk.Box):
                container.append(widget)
            elif isinstance(container, Gtk.Fixed):
                container.put(widget, x, y)
            elif isinstance(container, (Gtk.ApplicationWindow, Gtk.Popover, Gtk.Window)):
                container.set_child(widget)
            elif isinstance(container, Gtk.Frame):
                if hasattr(container, 'get_child') and container.get_child() is None:
                    container.set_child(widget)
                else:
                    self.logger.warning("Frame already has a child. Cannot attach another widget.")
            else:
                self.logger.error(f"Container of type {type(container).__name__} does not support pack_start or attach")
                raise TypeError(f"Unsupported container type {type(container).__name__}")
        except Exception as e:
            self.logger.error(f"Failed to attach widget: {e}")

    def create_scrolled_window(self, **kwargs):
        # Create a new Gtk.ScrolledWindow
        try:
            scrolled = Gtk.ScrolledWindow()
            if 'policy' in kwargs:
                scrolled.set_policy(kwargs['policy'][0], kwargs['policy'][1])
            if 'hexpand' in kwargs:
                scrolled.set_hexpand(kwargs['hexpand'])
            if 'vexpand' in kwargs:
                scrolled.set_vexpand(kwargs['vexpand'])
            self._set_margins(scrolled, **kwargs)
            return scrolled
        except Exception as e:
            self.logger.error(f"Failed to create scrolled window: {e}")
            return None

    def create_frame(self, **kwargs):
        # Create a new Gtk.Frame
        try:
            frame = Gtk.Frame()
            if 'size_request' in kwargs:
                frame.set_size_request(kwargs['size_request'][0], kwargs['size_request'][1])
            self._set_margins(frame, **kwargs)
            return frame
        except Exception as e:
            self.logger.error(f"Failed to create frame: {e}")
            return None

    def create_overlay(self, **kwargs):
        # Create a new Gtk.Overlay
        try:
            overlay = Gtk.Overlay()
            self._set_margins(overlay, **kwargs)
            return overlay
        except Exception as e:
            self.logger.error(f"Failed to create overlay: {e}")
            return None

    def create_flowbox(self, **kwargs):
        # Create a new Gtk.FlowBox
        try:
            flowbox = Gtk.FlowBox()
            if 'valign' in kwargs:
                flowbox.set_valign(kwargs['valign'])
            if 'max_children_per_line' in kwargs:
                flowbox.set_max_children_per_line(kwargs['max_children_per_line'])
            if 'min_children_per_line' in kwargs:
                flowbox.set_min_children_per_line(kwargs['min_children_per_line'])
            if 'row_spacing' in kwargs:
                flowbox.set_row_spacing(kwargs['row_spacing'])
            if 'column_spacing' in kwargs:
                flowbox.set_column_spacing(kwargs['column_spacing'])
            if 'homogeneous' in kwargs:
                flowbox.set_homogeneous(kwargs['homogeneous'])
            if 'selection_mode' in kwargs:
                flowbox.set_selection_mode(kwargs['selection_mode'])
            self._set_margins(flowbox, **kwargs)
            return flowbox
        except Exception as e:
            self.logger.error(f"Failed to create flowbox: {e}")
            return None

    def create_listbox(self, **kwargs):
        # Create a new Gtk.ListBox
        try:
            listbox = Gtk.ListBox()
            if 'selection_mode' in kwargs:
                listbox.set_selection_mode(kwargs['selection_mode'])
            self._set_margins(listbox, **kwargs)
            return listbox
        except Exception as e:
            self.logger.error(f"Failed to create listbox: {e}")
            return None

    def create_listbox_row(self, **kwargs):
        # Create a new Gtk.ListBoxRow
        try:
            row = Gtk.ListBoxRow()
            self._set_margins(row, **kwargs)
            return row
        except Exception as e:
            self.logger.error(f"Failed to create listbox row: {e}")
            return None

    def create_image(self, icon_name=None, file_path=None, **kwargs):
        # Create a new Gtk.Image
        try:
            if file_path:
                image = Gtk.Image.new_from_file(file_path)
            elif icon_name:
                image = Gtk.Image.new_from_icon_name(icon_name)
            else:
                image = Gtk.Image()
            if 'icon_size' in kwargs:
                image.set_icon_size(kwargs['icon_size'])
            self._set_margins(image, **kwargs)
            return image
        except Exception as e:
            self.logger.error(f"Failed to create image: {e}")
            return None

    def create_stack(self, **kwargs):
        # Create a new Gtk.Stack
        try:
            stack = Gtk.Stack()
            if 'hexpand' in kwargs:
                stack.set_hexpand(kwargs['hexpand'])
            if 'vexpand' in kwargs:
                stack.set_vexpand(kwargs['vexpand'])
            self._set_margins(stack, **kwargs)
            return stack
        except Exception as e:
            self.logger.error(f"Failed to create stack: {e}")
            return None

    def create_popover(self, **kwargs):
        # Create a new Gtk.Popover
        try:
            popover = Gtk.Popover()
            if 'position' in kwargs:
                popover.set_position(kwargs['position'])
            self._set_margins(popover, **kwargs)
            return popover
        except Exception as e:
            self.logger.error(f"Failed to create popover: {e}")
            return None

    def create_horizontal_box(self, **kwargs):
        # Create a new horizontal Gtk.Box
        try:
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            if 'spacing' in kwargs:
                box.set_spacing(kwargs['spacing'])
            if 'hexpand' in kwargs:
                box.set_hexpand(kwargs['hexpand'])
            if 'vexpand' in kwargs:
                box.set_vexpand(kwargs['vexpand'])
            if 'homogeneous' in kwargs:
                box.set_homogeneous(kwargs['homogeneous'])
            self._set_margins(box, **kwargs)
            return box
        except Exception as e:
            self.logger.error(f"Failed to create horizontal box: {e}")
            return None

    def create_vertical_box(self, **kwargs):
        # Create a new vertical Gtk.Box
        try:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            if 'spacing' in kwargs:
                box.set_spacing(kwargs['spacing'])
            if 'hexpand' in kwargs:
                box.set_hexpand(kwargs['hexpand'])
            if 'vexpand' in kwargs:
                box.set_vexpand(kwargs['vexpand'])
            if 'homogeneous' in kwargs:
                box.set_homogeneous(kwargs['homogeneous'])
            self._set_margins(box, **kwargs)
            return box
        except Exception as e:
            self.logger.error(f"Failed to create vertical box: {e}")
            return None

    def create_fixed(self, **kwargs):
        # Create a new Gtk.Fixed
        try:
            fixed = Gtk.Fixed()
            self._set_margins(fixed, **kwargs)
            return fixed
        except Exception as e:
            self.logger.error(f"Failed to create fixed: {e}")
            return None

    def create_application_window(self, application=None, **kwargs):
        # Create a new Gtk.ApplicationWindow
        try:
            window = Gtk.ApplicationWindow(application=application)
            self._set_margins(window, **kwargs)
            return window
        except Exception as e:
            self.logger.error(f"Failed to create application window: {e}")
            return None

    def create_adjustment(self, lower=0, upper=100, step_increment=1, **kwargs):
        # Create a new Gtk.Adjustment
        try:
            adjustment = Gtk.Adjustment(lower=lower, upper=upper, step_increment=step_increment)
            return adjustment
        except Exception as e:
            self.logger.error(f"Failed to create adjustment: {e}")
            return None

    def create_scale_widget(self, orientation=Gtk.Orientation.HORIZONTAL, adjustment=None, **kwargs):
        # Create a new Gtk.Scale widget (different from the overlay scale in create_scale)
        try:
            if adjustment:
                scale = Gtk.Scale(orientation=orientation, adjustment=adjustment)
            else:
                scale = Gtk.Scale(orientation=orientation)
            scale.set_draw_value(False)
            self._set_margins(scale, **kwargs)
            return scale
        except Exception as e:
            self.logger.error(f"Failed to create scale widget: {e}")
            return None

    def create_string_list(self, items=None, **kwargs):
        # Create a new Gtk.StringList
        try:
            string_list = Gtk.StringList()
            if items:
                for item in items:
                    string_list.append(item)
            return string_list
        except Exception as e:
            self.logger.error(f"Failed to create string list: {e}")
            return None

    def create_tree_store(self, column_types, **kwargs):
        # Create a new Gtk.TreeStore
        try:
            tree_store = Gtk.TreeStore(*column_types)
            return tree_store
        except Exception as e:
            self.logger.error(f"Failed to create tree store: {e}")
            return None

    def create_list_store(self, column_types, **kwargs):
        # Create a new Gtk.ListStore
        try:
            list_store = Gtk.ListStore(*column_types)
            return list_store
        except Exception as e:
            self.logger.error(f"Failed to create list store: {e}")
            return None

    def create_tree_view(self, model=None, **kwargs):
        # Create a new Gtk.TreeView
        try:
            if model:
                tree_view = Gtk.TreeView(model=model)
            else:
                tree_view = Gtk.TreeView()
            self._set_margins(tree_view, **kwargs)
            return tree_view
        except Exception as e:
            self.logger.error(f"Failed to create tree view: {e}")
            return None

    def create_cell_renderer_text(self, **kwargs):
        # Create a new Gtk.CellRendererText
        try:
            renderer = Gtk.CellRendererText()
            return renderer
        except Exception as e:
            self.logger.error(f"Failed to create cell renderer text: {e}")
            return None

    def create_tree_view_column(self, title, renderer, text_column=None, **kwargs):
        # Create a new Gtk.TreeViewColumn
        try:
            if text_column is not None:
                column = Gtk.TreeViewColumn(title, renderer, text=text_column)
            else:
                column = Gtk.TreeViewColumn(title, renderer)
            return column
        except Exception as e:
            self.logger.error(f"Failed to create tree view column: {e}")
            return None

    def create_popover_menu(self, **kwargs):
        # Create a new Gtk.PopoverMenu
        try:
            popover_menu = Gtk.PopoverMenu()
            self._set_margins(popover_menu, **kwargs)
            return popover_menu
        except Exception as e:
            self.logger.error(f"Failed to create popover menu: {e}")
            return None

    def create_message_dialog(self, transient_for=None, flags=0, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text="", secondary_text=None, **kwargs):
        # Create a new Gtk.MessageDialog
        try:
            # In GTK4, combine primary and secondary text
            combined_text = text
            if secondary_text:
                combined_text = f"{text}\n\n{secondary_text}"
            
            dialog = Gtk.MessageDialog(
                transient_for=transient_for,
                message_type=message_type,
                buttons=buttons,
                text=combined_text
            )
            
            # Set dialog as modal for proper interaction
            if transient_for:
                dialog.set_modal(True)
            
            return dialog
        except Exception as e:
            self.logger.error(f"Failed to create message dialog: {e}")
            return None

    def create_dialog(self, title="", transient_for=None, **kwargs):
        # Create a new Gtk.Dialog
        try:
            dialog = Gtk.Dialog(title=title)
            if transient_for:
                dialog.set_transient_for(transient_for)
            return dialog
        except Exception as e:
            self.logger.error(f"Failed to create dialog: {e}")
            return None

    def create_text_view(self, **kwargs):
        # Create a new Gtk.TextView
        try:
            text_view = Gtk.TextView()
            self._set_margins(text_view, **kwargs)
            return text_view
        except Exception as e:
            self.logger.error(f"Failed to create text view: {e}")
            return None

    def create_css_provider(self, **kwargs):
        # Create a new Gtk.CssProvider
        try:
            css_provider = Gtk.CssProvider()
            return css_provider
        except Exception as e:
            self.logger.error(f"Failed to create CSS provider: {e}")
            return None

    def create_rectangle(self, **kwargs):
        # Create a new Gdk.Rectangle
        try:
            rectangle = Gdk.Rectangle()
            return rectangle
        except Exception as e:
            self.logger.error(f"Failed to create rectangle: {e}")
            return None

    def create_gesture_click(self, **kwargs):
        # Create a new Gtk.GestureClick
        try:
            gesture = Gtk.GestureClick.new()
            return gesture
        except Exception as e:
            self.logger.error(f"Failed to create gesture click: {e}")
            return None

    def _set_margins(self, widget, **kwargs):
        # Set margins for a widget if specified in kwargs
        margin_properties = {
            'margin_start': widget.set_margin_start,
            'margin_end': widget.set_margin_end,
            'margin_top': widget.set_margin_top,
            'margin_bottom': widget.set_margin_bottom,
        }
        for prop, setter in margin_properties.items():
            if prop in kwargs and kwargs[prop] is not None:
                setter(kwargs[prop])
