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
/*global define */

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/_base/fx",
	"dojo/on",
	"dojo/mouse",
	"dojo/query",
	"dojo/dom-style",
	"dojo/dom-class",
	"dojo/topic",
	"dijit/layout/BorderContainer",
	"umc/tools",
	"umc/render",
	"umc/widgets/Text",
	"umc/widgets/ContainerWidget",
	"umc/i18n!umc/app"
], function(declare, lang, array, baseFX, on, mouse, query, style, domClass, topic, BorderContainer, tools, render, Text, ContainerWidget, _) {
	return declare("umc.widgets.Page", BorderContainer, {
		// summary:
		//		Class that abstracts a displayable page for a module.
		//		Offers the possibility to enter a help text that is shown or not
		//		depending on the user preferences.
		//		The widget itself is also a container such that children widgets
		//		may be adde via the 'addChild()' method.

		// helpText: String
		//		Text that describes the module, will be displayed at the top of a page.
		helpText: '',

		// headerText: String
		//		Text that will be displayed as header title.
		headerText: '&lt;Title missing&gt;',

		// footer: Object[]?
		//		Optional array of dicts that describes buttons that shall be added
		//		to the footer. The default button will be displayed on the right
		footerButtons: null,

		// title: String
		//		Title of the page. This option is necessary for tab pages.
		title: '',

		// noFooter: Boolean
		//		Disable the page footer.
		noFooter: false,

		// forceHelpText: Boolean
		//		If set to true, forces the help text to be shown.
		forceHelpText: false,

		// the widget's class name as CSS class
		'class': 'umcPage',

		i18nClass: 'umc.app',

		gutters: false,

		//style: 'width: 100%; height: 100%;',

		_helpTextPane: null,
		_headerTextPane: null,
		_subscriptionHandle: null,
		_footer: null,
		_notes: null,
		_footerButtons: null,

		_setTitleAttr: function(title) {
			// dont set html attribute title
			// (looks weird)
			this._set('title', title);
		},

		_setHelpTextAttr: function(newVal) {
			this.helpText = newVal;
			if (this._helpTextPane) {
				this._helpTextPane.set('content', newVal);
				this.layout();
			}
		},

		_setHeaderTextAttr: function(newVal) {
			this.headerText = newVal;
			if (this._headerTextPane) {
				this._headerTextPane.set('content', '<h1>' + newVal + '</h1>');
				this.layout();
			}
		},

		postMixInProperties: function() {
			this.inherited(arguments);

			// remove title from the attributeMap
			delete this.attributeMap.title;

			// initiate array for notes
			this._notes = [];
		},

		buildRendering: function() {
			this.inherited(arguments);

			// add the header
			this._headerTextPane = new Text({
				content: '<h1>' + this.headerText + '</h1>',
				region: 'top',
				'class': 'umcPageHeader'
			});
			this.addChild(this._headerTextPane);

			if (tools.preferences('moduleHelpText') && this.helpText) {
				// display the module helpText
				this._createHelpTextPane();
				this.addChild(this._helpTextPane, 1);
			}

			if (!this.noFooter) {
				// create the footer container(s)
				this._footer = new ContainerWidget({
					region: 'bottom',
					'class': 'umcPageFooter'
				});
				this.addChild(this._footer);
				var footerLeft = new ContainerWidget({
					style: 'float: left'
				});
				this._footer.addChild(footerLeft);
				var footerRight = new ContainerWidget({
					style: 'float: right'
				});
				this._footer.addChild(footerRight);

				// render all buttons and add them to the footer
				if (this.footerButtons && this.footerButtons instanceof Array && this.footerButtons.length) {
					var buttons = render.buttons(this.footerButtons);
					array.forEach(buttons.$order$, function(ibutton) {
						if ('submit' == ibutton.type || ibutton.defaultButton || 'right' == ibutton.align) {
							footerRight.addChild(ibutton);
						}
						else {
							footerLeft.addChild(ibutton);
						}
					}, this);
					this._footerButtons = buttons;
				}
			}
		},

		postCreate: function() {
			this.inherited(arguments);

			if (this.forceHelpText) {
				// help text should be displayed in any case
				this.showDescription();
			}
			else {
				// register for events to hide the help text information
				this._subscriptionHandle = topic.subscribe('/umc/preferences/moduleHelpText', lang.hitch(this, function(show) {
					if (false === show) {
						this.hideDescription();
					}
					else {
						this.showDescription();
					}
				}));
			}
		},

		uninitialize: function() {
			// unsubscribe upon destruction
			if (this._subscriptionHandle) {
				this._subscriptionHandle.remove();
			}
		},

		_createHelpTextPane: function() {
			this._helpTextPane = new Text({
				content: this.helpText,
				region: 'top',
				'class': 'umcPageHelpText'
			});
		},

		addChild: function(child) {
			// use 'center' as default region
			if (!child.region) {
				child.region = 'center';
			}
			this.inherited(arguments);
		},

		showDescription: function() {
			// if we don't have a help text, ignore call
			if (this._helpTextPane || !this.helpText) {
				return;
			}

			// put the help text in a Text widget and then add it to the container
			// make the node transparent, yet displayable
			this._createHelpTextPane();
			style.set(this._helpTextPane.domNode, {
				opacity: 0,
				display: 'block'
			});
			this.addChild(this._helpTextPane, 1);
			//this.layout();

			// fade in the help text
			baseFX.fadeIn({
				node: this._helpTextPane.domNode,
				duration: 500
			}).play();
		},

		hideDescription: function() {
			// if we don't have a help text visible, ignore call
			if (!this._helpTextPane) {
				return;
			}

			// fade out the help text
			baseFX.fadeOut({
				node: this._helpTextPane.domNode,
				duration: 500,
				onEnd: lang.hitch(this, function() {
					// remove the text from the layout and destroy widget
					this.removeChild(this._helpTextPane);
					this._helpTextPane.destroyRecursive();
					this._helpTextPane = null;
					//this.layout();
				})
			}).play();
		},

		addNote: function(message) {
			var closeButton = '<span class="dijitTabCloseButton dijitTabCloseIcon" style="float:right" title="Close"></span>';

			var note = new Text({
				content: closeButton + '<b>' + _('Note') + ':</b> ' + message,
				region: 'top',
				'class': 'umcPageNote'
			});
			query('.dijitTabCloseButton', note.domNode).forEach(function(inode) {
				this.own(on(inode, 'mousedown', function() {
					domClass.add(inode, 'dijitTabCloseButtonActive');
				}));
				this.own(on(inode, 'mouseup', function() {
					domClass.remove(inode, 'dijitTabCloseButtonActive');
				}));
				this.own(on(inode, mouse.enter, function() {
					domClass.add(inode, 'dijitTabCloseButtonHover');
				}));
				this.own(on(inode, mouse.leave, function() {
					domClass.remove(inode, 'dijitTabCloseButtonHover');
				}));
				this.own(on(inode, 'click', lang.hitch(this, function() {
					baseFX.fadeOut({
						node: note.domNode,
						duration: 500,
						onEnd: lang.hitch(this, function() {
							this.removeChild(note);
							note.destroyRecursive();
							this._notes = array.filter( this._notes, function( inote ) {
								return inote !== note;
							} );
						})
					}).play();
				})));
			}, this);
			this.addChild(note);
			this._notes.push(note);
			return note;
		},

		clearNotes: function() {
			array.forEach(this._notes, function(inote) {
				this.removeChild(inote);
				inote.destroyRecursive();
			}, this);
			this._notes = [];
		},

		startup: function() {
			this.inherited(arguments);

			// FIXME: Workaround for refreshing problems with datagrids when they are rendered
			//        on an inactive tab.

			// iterate over all widgets
			array.forEach(this.getDescendants(), function(iwidget) {
				if (tools.inheritsFrom(iwidget, 'dojox.grid._Grid')) {
					// hook to onShow event
					this.on('show', lang.hitch(this, function() {
						iwidget.startup();
					}));
				}
			}, this);
		}
	});
});

