/*
 * Copyright 2011-2012 Univention GmbH
 *
 * http://www.univention.de/
 *
 * All rights reserved.
 *
 * The source code of this program is made available
 * under the terms of the GNU Affero General Public License version 3
 * (GNU AGPL V3) as published by the Free Software Foundation.
 *
 * Binary versions of this program provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention and not subject to the GNU AGPL V3.
 *
 * In the case you use this program under the terms of the GNU AGPL V3,
 * the program is provided in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License with the Debian GNU/Linux or Univention distribution in file
 * /usr/share/common-licenses/AGPL-3; if not, see
 * <http://www.gnu.org/licenses/>.
 */
/*global define console */

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/Deferred",
	"dojo/dom-class",
	"dojo/dom-attr",
	"dijit/_WidgetBase",
	"dijit/_TemplatedMixin",
	"dijit/_Container",
	"umc/tools"
], function(declare, lang, Deferred, domClass, attr, _WidgetBase, _TemplatedMixin, _Container, tools) {
	lang.extend(_WidgetBase, {
		// isLabelDisplayed: Boolean?
		//		If specified as true, LabelPane assumes that the widget itself will take
		//		care of displaying the label correctly.
		//		This property is specified by `umc/widgets/LabelPane`.
		isLabelDisplayed: false,

		// visible: Boolean?
		//		If set to false, the label and widget will be hidden.
		visible: true
	});

	return declare("umc.widgets.LabelPane", [ _WidgetBase, _TemplatedMixin, _Container ], {
		// summary:
		//		Simple widget that displays a widget/HTML code with a label above.

		// don't use float, use display:inline-block; we need a hack for IE7 here, see:
		//   http://robertnyman.com/2010/02/24/css-display-inline-block-why-it-rocks-and-why-it-sucks/
		templateString: '<div style="display:inline-block;vertical-align:top;zoom:1;*display:inline;" class="umcLabelPane">' +
			'<div class="umcLabelPaneLabelNode umcLabelPaneLabeNodeTop" style="display:block;"><label dojoAttachPoint="labelNodeTop" for=""></label></div>' +
			'<span dojoAttachPoint="containerNode,contentNode" style=""></span>' +
			'<span class="umcLabelPaneLabelNode umcLabelPaneLabeNodeRight" style=""><label dojoAttachPoint="labelNodeRight" for=""></label></span>' +
			'</div>',

		// content: String|dijit/_WidgetBase
		//		String which contains the text (or HTML code) to be rendered or
		//		a dijit/_WidgetBase instance.
		content: '',

		// disabled: Boolean
		//		if the content of the label pane should be disabled. the content widgets must support it
		disabled: false,

		// the widget's class name as CSS class
		'class': 'umcLabelPane',

		// label: String
		label: null,

		labelNodeTop: null,

		labelNodeRight: null,

		_startupDeferred: null,

		constructor: function(params) {
			this._startupDeferred = new Deferred();

			// lang._mixin() would not work sometimes, leaving this.content empty, see
			//   https://forge.univention.org/bugzilla/show_bug.cgi?id=26214#c3
			tools.forIn(params, function(ikey, ival) {
				this[ikey] = ival;
			}, this);
		},

		postMixInProperties: function() {
			this.inherited(arguments);

			// if we have a widget as content and label is not specified, use the widget's
			// label attribute
			if (null === this.label || undefined === this.label) {
				this.label = this.content.label || '';
			}
		},

		postCreate: function() {
			this.inherited(arguments);

			// register watch handler for label and visibility changes
			if (lang.getObject('content.watch', false, this)) {
				if (!tools.inheritsFrom(this.content, 'umc.widgets.Button')) {
					// only watch the label and required property if widget is not a button
					this.own(this.content.watch('label', lang.hitch(this, function(attr, oldVal, newVal) {
						this.set('label', this.content.get('label') || '');
					})));
					this.own(this.content.watch('required', lang.hitch(this, function(attr, oldVal, newVal) {
						this.set('label', this.content.get('label') || '');
					})));
				}
				this.own(this.content.watch('visible', lang.hitch(this, function(attr, oldVal, newVal) {
					domClass.toggle(this.domNode, 'dijitHidden', !newVal);
				})));
			}
			else if (typeof this.label != "string") {
				this.label = '';
			}
		},

		buildRendering: function() {
			this.inherited(arguments);

			domClass.toggle(this.domNode, 'dijitHidden', this.content.visible === false);
		},

		startup: function() {
			this.inherited(arguments);

			this._startupDeferred.resolve();
		},

		_setLabelAttr: function(label) {
			if (lang.getObject('content.isLabelDisplayed', false, this)) {
				// the widget displays the label itself
				return;
			}

			// if we have a widget which is required, add the string ' (*)' to the label
			if (lang.getObject('domNode', false, this.content) &&
					lang.getObject('declaredClass', false, this.content) &&
					lang.getObject('required', false, this.content)) {
				label = label + ' (*)';
			}
			this.label = label;

			// set the labels' 'for' attribute
			if (lang.getObject('id', false, this.content) && lang.getObject('declaredClass', false, this.content)) {
				attr.set(this.labelNodeRight, 'for', this.content.id);
				attr.set(this.labelNodeTop, 'for', this.content.id);
			}

			// only for check boxes, place the label right of the widget
			if (tools.inheritsFrom(this.content, 'dijit.form.CheckBox')) {
				attr.set(this.labelNodeRight, 'innerHTML', label);
				if (label) {
					attr.set(this.labelNodeTop, 'innerHTML', '');
					domClass.add(this.domNode, 'umcLabelPaneCheckBox');
				}
			}
			else {
				attr.set(this.labelNodeTop, 'innerHTML', label);
			}
		},

		_setContentAttr: function(content) {
			this.content = content;

			// we have a string
			if (typeof content == "string") {
				this.contentNode.innerHTML = content;
			}
			// if we have a widget, clear the content and hook in the domNode directly
			else if (lang.getObject('domNode', false, content) && lang.getObject('declaredClass', false, content)) {
				this.contentNode.innerHTML = '';
				this.addChild(content);
			}
			this.set( 'disabled', this.disabled );
		},

		_setDisabledAttr: function( value ) {
			if ( this.content ) {
				this.content.set( 'disabled', value );
			}
		}
	});
});
