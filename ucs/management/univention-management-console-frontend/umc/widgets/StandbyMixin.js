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
	"dojo/dom-construct",
	"dijit/_WidgetBase",
	"dojox/widget/Standby"
], function(declare, lang, Deferred, construct, _WidgetBase, Standby) {
	return declare("umc.widgets.StandbyMixin", _WidgetBase, {
		// summary:
		//		Mixin class to make a widget "standby-able"

		_standbyWidget: null,

		standbyOpacity: 0.75,

		_lastContent: null,

		_standbyStartedDeferred: null,

		postMixInProperties: function() {
			this.inherited(arguments);

			this._standbyStartedDeferred = new Deferred();
		},

		buildRendering: function() {
			this.inherited(arguments);

			// create a standby widget targeted at this module
			this._standbyWidget = this.own(new Standby({
				target: this.domNode,
				duration: 200,
				//zIndex: 99999999,
				opacity: this.standbyOpacity,
				color: '#FFF'
			}))[0];
			this.domNode.appendChild(this._standbyWidget.domNode);
			this._standbyWidget.startup();
		},

		startup: function() {
			this.inherited(arguments);
			this._standbyStartedDeferred.resolve();
		},

		_cleanUp: function() {
			if (this._lastContent && this._lastContent.declaredClass && this._lastContent.domNode) {
				// we got a widget as last element, remove it from the DOM
				try {
					this._standbyWidget._textNode.removeChild(this._lastContent.domNode);
				}
				catch(e) {
					console.log('Could remove standby widget from DOM:', e);
				}
				this._lastContent = null;
			}
		},

		_updateContent: function(content) {
			// type check of the content
			if (typeof content == "string") {
				// string
				this._cleanUp();
				this._standbyWidget.set('text', content);
				this._standbyWidget.set('centerIndicator', 'text');
			}
			else if (typeof content == "object" && content.declaredClass && content.domNode) {
				// widget
				if (!this._lastContent || this._lastContent != content) {
					// we only need to add a new widget to the DOM
					this._cleanUp();
					this._standbyWidget.set('text', '');
					this._standbyWidget.set('centerIndicator', 'text');

					// hook the given widget to the text node
					construct.place(content.domNode, this._standbyWidget._textNode);
					content.startup();
				}
			}
			else {
				// set default image
				this._cleanUp();
				this._standbyWidget.set('centerIndicator', 'image');
			}

			// cache the widget
			this._lastContent = content;
		},

		standby: function(/*Boolean*/ doStandby, /*mixed?*/ content) {
			this._standbyStartedDeferred.then(lang.hitch(this, function() {
				if (doStandby) {
					// update the content of the standby widget
					this._updateContent(content);

					// show standby widget
					this._standbyWidget.show();
				}
				else {
					// hide standby widget
					this._standbyWidget.hide();
				}
			}));
		}
	});
});

