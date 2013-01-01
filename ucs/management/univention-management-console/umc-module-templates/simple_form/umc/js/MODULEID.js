/*
 * Copyright 2012 Univention GmbH
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
/*global define*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/on",
	"dojo/topic",
	"umc/dialog",
	"umc/tools",
	"umc/widgets/Page",
	"umc/widgets/Form",
	"umc/widgets/ExpandingTitlePane",
	"umc/widgets/Module",
	"umc/widgets/TextBox",
	"umc/widgets/TextArea",
	"umc/i18n!/umc/modules/MODULEID"
], function(declare, lang, on, topic, dialog, tools, Page, Form, ExpandingTitlePane, Module, TextBox, TextArea, _) {
	return declare("umc.modules.MODULEID", [ Module ], {
		// summary:
		//		Template module to ease the UMC module development.
		// description:
		//		This module is a template module in order to aid the development of
		//		new modules for Univention Management Console.

		postMixInProperties: function() {
			// is called after all inherited properties/methods have been mixed
			// into the object (originates from dijit._Widget)

			// it is important to call the parent's postMixInProperties() method
			this.inherited(arguments);

			// Set the opacity for the standby animation to 100% in order to mask
			// GUI changes when the module is opened. Call this.standby(true|false)
			// to enabled/disable the animation.
			this.standbyOpacity = 1;
		},

		buildRendering: function() {
			// is called after all DOM nodes have been setup
			// (originates from dijit._Widget)

			// it is important to call the parent's buildRendering() method
			this.inherited(arguments);

			// start the standby animation in order prevent any interaction before the
			// form values are loaded
			this.standby(true);

			// render the page containing search form and grid
			this.umcpCommand( 'MODULEID/configuration' ).then( lang.hitch( this, function( response ) {
				if ( response.result.sender ) {
					this.renderPage( response.result );
					this.standby( false );
				} else {
					dialog.alert( _( 'The MODULEID module is not configured properly' ) );
				}
			} ) );
		},

		renderPage: function( defaultValues ) {
			// umc.widgets.ExpandingTitlePane is an extension of dijit.layout.BorderContainer
			var titlePane = new ExpandingTitlePane( {
				title: _( 'Sending a message' )
			} );

			//
			// form
			//

			// add remaining elements of the search form
			var widgets = [ {
				type: TextBox,
				name: 'sender',
				label: _( 'Sender' ),
				value: defaultValues.sender,
				editable: false
			}, {
				type: TextBox,
				name: 'recipient',
				label: _('Recipient'),
				value: defaultValues.recipient
			}, {
				type: TextBox,
				name: 'subject',
				label: _('Subject'),
				value: defaultValues.subject
			}, {
				type: TextArea,
				name: 'message',
				label: _( 'Message' )
			} ];

			// the layout is an 2D array that defines the organization of the form elements...
			// here we arrange the form elements in one row and add the 'submit' button
			var layout = [
				'sender',
				'recipient',
				'subject',
				'message'
			];

			// generate the form
			this._form = new Form({
				// property that defines the widget's position in a dijit.layout.BorderContainer
				region: 'top',
				widgets: widgets,
				layout: layout,
				scrollable: true
			});

			// turn off the standby animation as soon as all form values have been loaded
			on.once(this._form, 'valuesInitialized', function() {
				this.standby( false );
			});

			// add form to the title pane
			titlePane.addChild(this._form);

			// submit changes
			var buttons = [ {
				name: 'submit',
				label: _( 'Send' ),
				'default': true,
				callback: lang.hitch( this, function() {
					var values = this._form.gatherFormValues();
					if ( values.message ) {
						this.onSubmit( this._form.gatherFormValues() );
					} else {
						dialog.alert( 'A message is missing!' );
					}
				} )
			}, {
				name: 'close',
				label: _('Close'),
				callback: lang.hitch(this, function() {
					var values = this._form.gatherFormValues();
					if ( values.message ) {
						dialog.confirm( _( 'Should the UMC module be closed? All unsaved modification will be lost.' ), [ {
							label: _( 'Close' ),
							callback: lang.hitch( this, function() {
								topic.publish('/umc/tabs/close', [ this ] );
							} )
						}, {
							label: _( 'Cancel' ),
							'default': true
						} ] );
					} else {
						topic.publish('/umc/tabs/close', [ this ] );
					}
				} )
			} ];

			this._page = new Page({
				headerText: this.description,
				helpText: '',
				footerButtons: buttons
			});

			this.addChild(this._page);
			this._page.addChild( titlePane );
		},

		onSubmit: function( values ) {
			this.umcpCommand( 'MODULEID/send', values ).then( lang.hitch( this, function ( response ) {
				if ( response.result ) {
					dialog.alert( _( 'The message has been sent' ) );
					this._form._widgets.message.set( 'value', '' );
				} else {
					dialog.alert( _( 'The message could not be send: ' ) + response.message );
				}
			} ) );
		}
	});
});
