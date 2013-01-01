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
/*global define*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/on",
	"dojo/Deferred",
	"dojo/promise/all",
	"dojo/dom-style",
	"dojo/dom-construct",
	"dojo/dom-class",
	"dojo/topic",
	"dojo/json",
	"dijit/TitlePane",
	"dijit/layout/BorderContainer",
	"dijit/layout/ContentPane",
	"umc/render",
	"umc/tools",
	"umc/dialog",
	"umc/widgets/ContainerWidget",
	"umc/widgets/Form",
	"umc/widgets/Page",
	"umc/widgets/StandbyMixin",
	"umc/widgets/TabContainer",
	"umc/widgets/Text",
	"umc/widgets/Button",
	"umc/widgets/ComboBox",
	"umc/widgets/LabelPane",
	"umc/modules/udm/Template",
	"umc/modules/udm/OverwriteLabel",
	"umc/modules/udm/UMCPBundle",
	"umc/i18n!umc/modules/udm",
	"dijit/registry",
	"umc/widgets"
], function(declare, lang, array, on, Deferred, all, style, construct, domClass, topic, json, TitlePane, BorderContainer, ContentPane, render, tools, dialog, ContainerWidget, Form, Page, StandbyMixin, TabContainer, Text, Button, ComboBox, LabelPane, Template, OverwriteLabel, UMCPBundle, _ ) {
	return declare("umc.modules.udm.DetailPage", [ ContentPane, StandbyMixin ], {
		// summary:
		//		This class renderes a detail page containing subtabs and form elements
		//		in order to edit UDM objects.

		// umcpCommand: Function
		//		Reference to the module specific umcpCommand function.
		umcpCommand: null,

		// moduleStore: Object
		//		Reference to the module's module store.
		moduleStore: null,

		// moduleFlavor: String
		//		Flavor of the module
		moduleFlavor: this.moduleFlavor,

		// objectType: String
		//		The object type of the UDM object that is edited.
		objectType: null,

		// ldapName: String?|String[]?
		//		The LDAP DN of the object that is edited. This property needs not to be set
		//		when a new object is edited. Can also be a list of LDAP DNs for multi-edit
		//		mode.
		ldapName: null,

		// newObjectOptions:
		// 		Dict containing options for creating a new UDM object (chosen by the user
		// 		in the 'add object' dialog). This includes properties such as superordinate,
		//		the container in wich the object is to be created, the object type etc.
		newObjectOptions: null,

		// isCloseable: Boolean?
		//		Specifies whether this
		isClosable: false,

		// note: String?
		//		If given, this string is displayed as note on the first page.
		note: null,

		// internal reference to the formular containing all form widgets of an UDM object
		_form: null,

		// internal reference to the page containing the subtabs for object properties
		_tabs: null,

		// internal reference to a dict with entries of the form: policy-type -> widgets
		_policyWidgets: null,

		// Deferred object of the query and render process for the policy widgets
		_policyDeferred: null,

		// object properties as they are received from the server
		_receivedObjOrigData: null,

		// initial object properties as they are represented by the form
		_receivedObjFormData: null,

		// UDM object type of the current edited object
		_editedObjType: null,

		// dict that saves which form element is displayed on which subtab
		// (used to display user input errors)
		_propertySubTabMap: null,

		// dict that saves the options that must be set for a property to be available
		_propertyOptionMap: null,

		// array that stores extra references to all sub tabs
		// (necessary to reset change sub tab titles [when displaying input errors])
		_detailPages: null,

		// reference to the policies tab
		_policiesTab: null,

		// the widget of the options if available
		_optionsWidget: null,

		// reference to the template object in order to monitor user input changes
		_template: null,

		ldapBase: null,

		_multiEdit: false,

		_bundledCommands: null,

		// UDM object type name in singular and plural
		objectNameSingular: '',
		objectNamePlural: '',

		postMixInProperties: function() {
			this.inherited(arguments);

			this.standbyOpacity = 1;
			this._multiEdit = this.ldapName instanceof Array;
		},

		buildRendering: function() {
			// summary:
			//		Query necessary information from the server for the object detail page
			//		and initiate the rendering process.
			this.inherited(arguments);

			// remember the objectType of the object we are going to edit
			this._editedObjType = this.objectType;

			// for the detail page, we first need to query property data from the server
			// for the layout of the selected object type, then we can render the page
			var params = {
				objectType: this.objectType,
				// when editing multiple items, get the properties as for a new object
				objectDN: this._multiEdit ? null : this.ldapName || null
			};

			// udm/objects/properties will be bundled
			this._bundledCommands = {};

			// prepare parallel queries
			var commands = {
				properties: this.umcpCommandBundle('udm/properties', params),
				layout: this.umcpCommandBundle('udm/layout', params)
			};
			if (!this._multiEdit) {
				// query policies for normal edit
				commands.policies = this.umcpCommand('udm/policies', params);
			} else {
				// for multi-edit, mimic an empty list of policies
				commands.policies = new Deferred();
				commands.policies.resolve();
			}
			commands.ucr = tools.ucr( [ 'ldap/base' ] );

			// in case an object template has been chosen, add the umcp request for the template
			var objTemplate = lang.getObject('objectTemplate', false, this.newObjectOptions);
			if (objTemplate && 'None' != objTemplate) {
				commands.template = this.umcpCommand('udm/get', [objTemplate], true, 'settings/usertemplate');
			}

			// when the commands have been finished, create the detail page
			this.standby(true);
			(new all(commands)).then(lang.hitch(this, function(results) {
				var properties = lang.getObject('properties.result', false, results);
				var layout = lang.getObject('layout.result', false, results);
				var policies = lang.getObject('policies.result', false, results);
				this.ldapBase = results.ucr[ 'ldap/base' ];
				var template = lang.getObject('template.result', false, results) || null;
				this.renderDetailPage(properties, layout, policies, template).then(lang.hitch(this, function() {
					this.standby(false);
				}), lang.hitch(this, function() {
					this.standby(false);
				}));
			}), lang.hitch(this, function() {
				this.standby(false);
			}), lang.hitch(this, function() {
				this.standby(false);
			}));
		},

		renderDetailPage: function(_properties, _layout, policies, _template) {
			// summary:
			//		Render the form with subtabs containing all object properties that can
			//		be edited by the user.

			if (_template && _template.length > 0) {
				_template = _template[0];
			} else {
				_template = null;
			}
			// create detail page
			this._tabs = new TabContainer({
				nested: true,
				region: 'center'
			});

			// parse the widget configurations
			var properties = [];
			var optionMap = {};
			_properties.push( {
				type: 'Text',
				id: '$objecttype$',
				content: '',
				style: 'padding-bottom: 5px;',
				label: ''
			} );
			_properties.push( {
				type: 'Text',
				id: '$location$',
				content: '',
				align: 'right',
				// style: 'padding-bottom: 10px;',
				label: ''
			} );
			array.forEach(_properties, function(iprop) {
				// ignore internal properties
				if ( iprop.id.slice( 0, 1 ) == '$' && iprop.id.slice( -1 ) == '$' ) {
					properties.push(iprop);
					return;
				}
				if ( 'LinkList' == iprop.type ) {
					iprop.multivalue = false;
				} else if ( iprop.type.indexOf('MultiObjectSelect') >= 0 ) {
					iprop.multivalue = false;
				} else if (iprop.multivalue && 'MultiInput' != iprop.type) {
					// handle multivalue inputs
					iprop.subtypes = [{
						type: iprop.type,
						dynamicValues: iprop.dynamicValues,
						dynamicValuesInfo: iprop.dynamicValuesInfo,
						dynamicOptions: iprop.dynamicOptions,
						staticValues: iprop.staticValues,
						size: iprop.size,
						depends: iprop.depends
					}];
					iprop.type = 'MultiInput';
				}

				// handle editable items
				if ( iprop.readonly ) {
					iprop.disabled = true;
				} else {
					iprop.disabled = this.ldapName === undefined ? false : ! iprop.editable;
				}
				if (this._multiEdit && iprop.identifies) {
					// in multi-edit mode, one cannot edit the 'name' field, i.e., the identifier
					iprop.disabled = true;
				}

				properties.push(iprop);
				optionMap[ iprop.id ] = iprop.options;
			}, this);
			this._propertyOptionMap = optionMap;

			// ### Advanved settings
			// parse the layout configuration... we would like to group all groups of advanced
			// settings on a special sub tab
			var advancedGroup = {
				label: _('[Advanced settings]'),
				description: _('Advanced settings'),
				layout: []
			};
			var layout = [];
			array.forEach(_layout, function(ilayout) {
				if (ilayout.advanced) {
					// advanced groups of settings should go into one single sub tab
					var jlayout = lang.mixin({ open: false }, ilayout);
					advancedGroup.layout.push(jlayout);
				} else {
					layout.push(ilayout);
				}
			});

			// if there are advanced settings, add them to the layout
			if (advancedGroup.layout.length) {
				layout.push(advancedGroup);
			}

			// ### Options
			var option_values = {};
			var option_prop = null;
			array.forEach( properties, function( item ) {
				if ( item.id == '$options$' ) {
					option_prop = item;
					return false;
				}
			} );
			if ( option_prop && option_prop.widgets.length > 0 && !this._multiEdit ) {
				var optiontab = {
					label: _( '[Options]' ),
					description: _( 'Options describing the basic features of the UDM object' ),
					layout: [ '$options$' ]
				};
				layout.push( optiontab );

				var option_widgets = [];
				var option_layout = [];
				var create = this.ldapName === undefined;
				array.forEach( option_prop.widgets, function ( option ) {
					option = lang.clone(option);
					// special case: bring options from template into the widget
					if (_template && _template._options) {
						option.value = _template._options.indexOf(option.id) > -1;
					}
					option_widgets.push( lang.mixin( {
						disabled: create ? false : ! option.editable
					}, option ) );
					option_values[ option.id ] = option.value;
					option_layout.push( option.id );
				} );
				option_prop.widgets = option_widgets;
				option_prop.layout = option_layout;
			} else {
				properties = array.filter( properties, function( item ) {
					return item.id != '$options$';
				} );
			}

			// special case for password, it is only required when a new user is added
			if (!this.newObjectOptions) {
				array.forEach(properties, function(iprop) {
					if ('password' == iprop.id) {
						iprop.required = false;
						return false;
					}
				});
			}

			// make sure that the widget use the flavored umcpCommand
			array.forEach( properties, function( iprop ) {
				iprop.umcpCommand = this.umcpCommand;
			}, this );


			// render all widgets
			var widgets = render.widgets( properties, this );

			// connect to onChange for the options property if it exists
			if ( '$options$' in widgets ) {
				this._optionsWidget = widgets.$options$;
				this.own(this._optionsWidget.watch('value', lang.hitch(this, function(attr, oldVal, newVal) {
					this.onOptionsChanged(newVal);
				})));
			}

			if (this._multiEdit) {
				this.moduleWidget.set( 'title', this.moduleWidget.defaultTitle + ' ' + _('(multi-edit)'));
			} else {
				// find property identifying the object
				tools.forIn( widgets, function( name, widget ) {
					if ( widget.identifies ) {
						// watch value and modify title (escaped)
						this.own(widget.watch('value', lang.hitch( this, function( attr, oldValue, _value ) {
							var value = _value instanceof Array ? _value.join( " " ) : _value;
							this.moduleWidget.set( 'titleDetail', value );
						} ) ) );
						return false; // break out of forIn
					}
				}, this );
			}

			// render the layout for each subtab
			this._propertySubTabMap = {}; // map to remember which form element is displayed on which subtab
			this._detailPages = [];

			layout[ 0 ].layout.unshift( [ '$objecttype$', '$location$' ] );
			array.forEach(layout, function(ilayout, i) {
				// create a new page, i.e., subtab
				var subTab = new Page({
					title: ilayout.label || ilayout.name, //TODO: 'name' should not be necessary
					noFooter: true,
					headerText: ilayout.description || ilayout.label || ilayout.name,
					helpText: ''
				});
				if (i === 0 && this.note) {
					// add the specified note to the first page
					subTab.addNote(this.note);
				}

				// add rendered layout to subtab and register subtab
				var subTabWidgets = render.layout(ilayout.layout, widgets);
				ilayout.$refSubTab$ = subTab;
				style.set(subTabWidgets.domNode, 'overflow', 'auto');
				subTab.addChild(subTabWidgets);
				this._tabs.addChild(subTab);

				// update _propertySubTabMap
				this._detailPages.push(subTab);
				var layoutStack = [ ilayout.layout ];
				while (layoutStack.length) {
					var ielement = layoutStack.pop();
					if (ielement instanceof Array) {
						layoutStack = layoutStack.concat(ielement);
					} else if (typeof ielement == "string") {
						this._propertySubTabMap[ielement] = subTab;
					} else if (ielement.layout) {
						layoutStack.push(ielement.layout);
					}
				}
			}, this);
			this._layoutMap = layout;

			if (this._multiEdit) {
				// in multi-edit mode, hook a 'overwrite?' checkbox after each widget
				tools.forIn(widgets, function(iname, iwidget) {
					if (iwidget.$refLabel$ && !iwidget.disabled) {
						iwidget.$refOverwrite$ = this.own(new OverwriteLabel({}))[0];
						construct.place(iwidget.$refOverwrite$.domNode, iwidget.$refLabel$.domNode);
					}
				}, this);
			}

			// #### Policies
			// in case we have policies that apply to the current object, we need an extra
			// sub tab that groups all policies together
			this._policyWidgets = {};
			if (policies && policies.length) {
				this._policiesTab = new Page({
					title: _('[Policies]'),
					noFooter: true,
					headerText: _('Properties inherited from policies'),
					helpText: _('List of all object properties that are inherited by policies. The values cannot be edited directly. In order to edit a policy, click on the "edit" button to open a particular policy in a new tab.')
				});
				this._tabs.addChild(this._policiesTab);
				var policiesContainer = new ContainerWidget({
					scrollable: true
				});
				this._policiesTab.addChild(policiesContainer);

				// we need to query for each policy object its properties and its layout
				// this can be done asynchronously
				var commands = [];
				array.forEach(policies, function(ipolicy) {
					var params = { objectType: ipolicy.objectType };
					commands.push(this.umcpCommandBundle('udm/properties', params));
					commands.push(this.umcpCommandBundle('udm/layout', params));
				}, this);

				// wait until we have results for all queries
				this._policyDeferred = all(commands).then(lang.hitch(this, function(results) {
					// parse the widget configurations
					var i;
					for (i = 0; i < results.length; i += 2) {
						var ipolicy = policies[Math.floor(i / 2)];
						var ipolicyType = ipolicy.objectType;
						var iproperties = results[i].result;
						var ilayout = results[i + 1].result;
						var newLayout = [];

						// we only need to show the general properties of the policy... the "advanced"
						// properties would be rendered on the subtab "advanced settings" which we do
						// not need in this case
						array.forEach(ilayout, function(jlayout) {
							if (false === jlayout.advanced) {
								// we found the general properties of the policy
								newLayout = jlayout.layout;

								// break the loop
								return false;
							}
						});

						// build up a small map that indicates which policy properties will be shown
						// filter out the property 'name'
						var usedProperties = {};
						array.forEach(newLayout, function(jlayout) {
						   if ( jlayout instanceof Array || typeof jlayout == "object" ) {
							   var nestedLayout = (undefined === jlayout.layout) ? jlayout : jlayout.layout;
								array.forEach( nestedLayout, function(klayout) {
									array.forEach(tools.stringOrArray(klayout), function(llayout) {
										if (typeof llayout == "string") {
											if ('name' != llayout) {
												usedProperties[llayout] = true;
											}
										}
									});
								});
							} else if (typeof jlayout == "string") {
								if ('name' != jlayout) {
									usedProperties[jlayout] = true;
								}
							}
						});

						// get only the properties that need to be rendered
						var newProperties = [];
						array.forEach(iproperties, function(jprop) {
							var jname = jprop.id || jprop.name;
							if (jname in usedProperties) {
								if (jprop.multivalue && 'MultiInput' != jprop.type) {
									// handle multivalue inputs
									jprop.subtypes = [{
										type: jprop.type,
										dynamicValues: jprop.dynamicValues,
										dynamicValuesInfo: jprop.dynamicValuesInfo,
										dynamicOptions: jprop.dynamicOptions,
										staticValues: jprop.staticValues,
										size: jprop.size,
										depends: jprop.depends
									}];
									jprop.type = 'MultiInput';
								}
								jprop.disabled = true; // policies cannot be edited
								jprop.$orgLabel$ = jprop.label; // we need the original label
								newProperties.push(jprop);
							}
						}, this);

						// make sure that the widget use the flavored umcpCommand
						array.forEach( newProperties, function( iprop ) {
							iprop.umcpCommand = this.umcpCommand;
						}, this );

						// for the policy group, we need a ComboBox that allows to link an object
						// to a particular policy
						newProperties.push({
							type: ComboBox,
							name: '$policy$',
							staticValues: [{ id: 'None', label: _('Inherited') }],
							dynamicValues: lang.hitch(this, '_queryPolicies', ipolicyType),
							label: _('Select policy configuration'),
							description: _('Select a policy that should be directly linked to the current UDM object'),
							onChange: lang.hitch(this, '_updatePolicy', ipolicyType)
						});
						var buttonsConf = [{
							type: Button,
							name: '$addPolicy$',
							iconClass: 'umcIconAdd',
							label: _('Create new policy'),
							callback: lang.hitch(this, '_openPolicy', ipolicyType, undefined)
						}];
						newLayout.unshift(['$policy$', '$addPolicy$']);

						// render the group of properties
						var widgets = render.widgets(newProperties, this);
						this._policyWidgets[ipolicyType] = widgets;
						var buttons = render.buttons(buttonsConf, this);
						policiesContainer.addChild(new TitlePane({
							title: ipolicy.label,
							description: ipolicy.description,
							open: false,
							content: render.layout(newLayout, widgets, buttons)
						}));
					}
				}));
			} else {
				// in case there are no policies, we use a dummy Deferred object
				this._policyDeferred = new Deferred();
				this._policyDeferred.resolve();
			}

			// setup detail page, needs to be wrapped by a form (for managing the
			// form entries) and a BorderContainer (for the footer with buttons)
			var borderLayout = this.own(new BorderContainer({
				gutters: false
			}))[0];
			borderLayout.addChild(this._tabs);

			var closeLabel = _('Back to search');
			if ('navigation' == this.moduleFlavor) {
				closeLabel = _('Back to LDAP directory tree');
			}
			if (this.isClosable) {
				closeLabel = _('Cancel');
			}

			var createLabel = '';
			if (this.newObjectOptions) {
				createLabel = _( 'Create %s', this.objectNameSingular );
			} else {
				createLabel = _( 'Save changes' );
			}

			// buttons
			var buttons = render.buttons([{
				name: 'submit',
				label: createLabel,
				style: 'float: right'
			}, {
				name: 'close',
				label: closeLabel,
				callback: lang.hitch(this, 'onCloseTab'),
				style: 'float: left'
			}], this);
			var footer = new ContainerWidget({
				'class': 'umcPageFooter',
				region: 'bottom'
			});
			array.forEach(buttons.$order$, function(i) {
				footer.addChild(i);
			});
			borderLayout.addChild(footer);
			borderLayout.startup();

			// create the form containing the whole BorderContainer as content and add
			// the form as content of this class
			this._form = this.own(new Form({
				widgets: widgets,
				content: borderLayout,
				moduleStore: this.moduleStore,
				onSubmit: lang.hitch(this, 'validateChanges')
			}))[0];
			this._policyDeferred.then(lang.hitch(this, function() {
				this.set('content', this._form);
			}));

			// set options
			if ( '$options$' in widgets && !this._multiEdit) {
				// required when creating a new object
				this._optionsWidget.set( 'value', option_values );
			}

			// initiate the template mechanism (only for new objects)
			if (!this.ldapName && !this._multiEdit) {
				// search for given default values in the properties... these will be replaced
				// by the template mechanism
				var template = {};
				array.forEach(_properties, function(iprop) {
					if (iprop['default']) {
						var defVal = iprop['default'];
						if (typeof defVal == "string" && iprop.multivalue) {
							defVal = [ defVal ];
						}
						template[iprop.id] = defVal;
					}
				});

				// mixin the values set in the template object (if given)
				if (_template) {
					tools.forIn(_template, lang.hitch(this, function(key, value) {
						// $dn$, $options$, etc of the template
						// should not be values for the object
						if ((/^\$.*\$$/).test(key)) {
							delete _template[key];
						}
						if ((/^_.+$/).test(key)) {
							var specialWidget = this[key + 'Widget'];
							// TODO: it may be important to solve this generically
							// by now, only _options will go this path
							// and _optionsWidget needs a special format
							var specialValue = {};
							array.forEach(value, function(val) {
								specialValue[val] = true;
							});
							if (specialWidget) {
								specialWidget.set('value', specialValue);
							}
							delete _template[key];
						}
					}));
					template = lang.mixin(template, _template);
				}

				// create a new template object that takes care of updating the elements in the form
				this._template = this.own(new Template({
					widgets: widgets,
					template: template
				}))[0];
			}

			// load form data
			if (this.ldapName && !this._multiEdit) {
				this._form.load(this.ldapName).then(lang.hitch(this, function(vals) {
					// save the original data we received from the server
					this._receivedObjOrigData = vals;

					// as soon as the policy widgets are rendered, update the policy values
					this._policyDeferred.then(lang.hitch(this, function() {
						var policies = lang.getObject('_receivedObjOrigData.$policies$', false, this) || {};
						tools.forIn(policies, function(ipolicyType, ipolicyDN) {
							// get the ComboBox to update its value with the new DN
							if (ipolicyType in this._policyWidgets) {
								var iwidget = this._policyWidgets[ipolicyType].$policy$;
								iwidget.setInitialValue(ipolicyDN, true);
							}
						}, this);
					}));

					// var objecttype = vals.$labelObjectType$;
					var path = tools.ldapDn2Path( this.ldapName, this.ldapBase );
					this._form.getWidget( '$objecttype$' ).set( 'content', _( 'Type: <i>%(type)s</i>', { type: vals.$labelObjectType$ } ) );
					this._form.getWidget( '$location$' ).set( 'content', _( 'Position: <i>%(path)s</i>', { path: path } ) );

					// save the original form data
					this._form.ready().then(lang.hitch(this, function() {
						this._receivedObjFormData = this.getValues();
						this._receivedObjFormData.$policies$ = this._receivedObjOrigData.$policies$;
					}));
				}));
			} else {
				// hide the type info and ldap path in case of a new object
				this._form.getWidget( '$objecttype$' ).set( 'visible', false);
				this._form.getWidget( '$location$' ).set( 'visible', false);
			}

			// return the policy deferred object to notify the caller that the page
			// has been set up
			return this._form.ready();
		},

		getValues: function() {
			// get all form values
			var vals = this._form.gatherFormValues();

			// get also policy values... can not be handled as standard form entry
			// explicitely exclude users/self. FIXME: find a way
			// to receive some udm-module-configuration for that
			if (this.objectType != 'users/self') {
				vals.$policies$ = {};
				tools.forIn(this._policyWidgets, function(ipolicyType, iwidgets) {
					var ival = iwidgets.$policy$.get('value');
					if ('None' != ival) {
						vals.$policies$[ipolicyType] = ival;
					}
				}, this);
			}

			return vals;
		},

		_queryPolicies: function(objectType) {
			return this.umcpCommand('udm/query', {
				objectType: objectType,
				container: 'all',
				objectProperty: 'None',
				objectPropertyValue: ''
			}).then(function(data) {
				return array.map(data.result, function(ientry) {
					return ientry.$dn$;
				});
			});
		},

		// TODO: this could very well go into tools.
		// for now, it is only tested to work with udm/object/policies
		umcpCommandBundle: function(command, params) {
			if (this._bundledCommands[command] === undefined) {
				this._bundledCommands[command] = new UMCPBundle(command, this.umcpCommand);
			}
			var bundle = this._bundledCommands[command];
			var deferred = bundle.addParams(params);
			return deferred;
		},

		_updatePolicy: function(policyType, policyDN) {
			// make sure the given policyType exists
			if (!(policyType in this._policyWidgets)) {
				return;
			}

			// evaluate the policy with the given policyType and policyDN
			this.umcpCommandBundle('udm/object/policies', {
				objectType: this.objectType,
				policyDN: 'None' == policyDN || !policyDN ? null : policyDN,
				policyType: policyType,
				objectDN: this.ldapName || null,
				container: this.newObjectOptions ? this.newObjectOptions.container : null 
			}).then(lang.hitch(this, function(data) {
				tools.forIn(this._policyWidgets[policyType], function(iname, iwidget) {
					if (iname == '$policy$') {
						// the ComboBox for policies, skip this widget
						return;
					}

					// set the value and label
					var iinfo = data.result[iname];
					var label = '';
					if (!iinfo) {
						// no policy values are inherited
						label = lang.replace('{label} (<span class="umcUnsetPolicy">{edit}</span>)', {
							label: iwidget.$orgLabel$,
							edit: _('not defined')
						});
						iwidget.set('label', label);
						if (!iinfo instanceof Array) {
							iwidget.set('value', '');
						} else {
							iwidget.set('value', []);
						}
					} else if (!(iinfo instanceof Array)) {
						// standard policy
						iwidget.set('value', iinfo.value);
						label = lang.replace('{label} (<a href="javascript:void(0)" ' +
								'onclick=\'require("dijit/registry").byId("{id}")._openPolicy("{type}", "{dn}")\' ' +
								'title="{title}: {dn}">{edit}</a>)', {
							label: iwidget.$orgLabel$,
							id: this.id,
							type: policyType,
							dn: iinfo.policy,
							title: _('Click to edit the inherited properties of the policy'),
							edit: _('edit')
						});
						iwidget.set('label', label);
					} else if (iinfo instanceof Array && tools.inheritsFrom(iwidget, 'umc.widgets.MultiInput')) {
						// we got probably a UCR-Policy, this is a special case:
						// -> a list of values where each value might have been inherited
						//    by different policies
						iwidget.set('value', array.map(iinfo, function(ival) {
							return ival.value;
						}));

						array.forEach(iinfo, function(jinfo, j) {
							if (iwidget._rowContainers.length < j) {
								// something is wrong... there are not enough entries it seems
								return false;
							}

							// prepare the HTML code to link to the policy
							var label = lang.replace('(<a href="javascript:void(0)" ' +
									'onclick=\'require("dijit/registry").byId("{id}")._openPolicy("{type}", "{dn}")\' ' +
									'title="{title}: {dn}">{edit}</a>)', {
								id: this.id,
								type: policyType,
								dn: jinfo.policy,
								title: _('Click to edit the inherited properties of the policy'),
								edit: _('edit')
							});

							var container = iwidget._rowContainers[j];
							if (!container.$linkWidget$) {
								// add an additional widget with the link the the UCR policy to the row
								container.$linkWidget$ = new LabelPane({
									label: j === 0 ? '&nbsp;' : '',
									content: new Text({
										content: label
									})
								});

								// get the correct row container
								container.addChild(container.$linkWidget$);
							} else {
								// link widget already exists, update its content
								container.$linkWidget$.set('content', label);
							}
						}, this);

						// make sure that the last row does not contain a link widget
						var lastContainer = iwidget._rowContainers[iwidget._rowContainers.length - 1];
						if (lastContainer.$linkWidget$) {
							lastContainer.removeChild(lastContainer.$linkWidget$);
							lastContainer.$linkWidget$.destroyRecursive();
							lastContainer.$linkWidget$ = null;
						}
					} else {
						// fallback
						var value = array.map( iinfo, function( item ) {
							return item.value;
						} );
						iwidget.set('value', value);
					}
				}, this);
			}));
		},

		_openPolicy: function(policyType, policyDN) {
			var props = {
				onObjectSaved: lang.hitch(this, function(dn, policyType) {
					// a new policy was created and should be linked to the current object
					// or an existing policy was modified
					if ((policyType in this._policyWidgets)) {
						// trigger a reload of the dynamicValues
						var widget = this._policyWidgets[policyType].$policy$;
						widget.reloadDynamicValues();

						// set the value after the reload has been done
						on.once(widget, 'valuesLoaded', lang.hitch(this, function() {
							var oldDN = widget.get('value');

							// we need to set the new DN, only if a new policy object has been created
							if (!policyDN) {
								widget.setInitialValue(dn, true);
							}
							if (oldDN == dn) {
								// we need a manual refresh in case the DN did not change since
								// the policy might have been edited and therefore its values
								// need to be reloaded
								this._updatePolicy(policyType, dn);
							}
						}));
					}
				}),
				onCloseTab: lang.hitch(this, function() {
					try {
						this.onFocusModule();
					}
					catch (e) { }
					return true;
				})
			};

			if (policyDN) {
				// policyDN is given, open an existing object
				props.openObject = {
					objectType: policyType,
					objectDN: policyDN,
					note: _('You are currently editing a policy. Changing its properties affects all referenced objects and may affect your system globally.')
				};
			} else {
				// if no DN is given, we are creating a new oject
				props.newObject = {
					objectType: policyType
				};
			}

			topic.publish('/umc/modules/open', 'udm', 'policies/policy', props);
		},

		onFocusModule: function() {
			// event stub
		},

		onOptionsChanged: function( newValue ) {
			var activeOptions = [];

			// retrieve active options
			tools.forIn( this._optionsWidget.get( 'value' ), function( item, value ) {
				if ( value === true ) {
					activeOptions.push( item );
				}
			} );

			// hide/show widgets
			tools.forIn( this._propertyOptionMap, lang.hitch( this, function( prop, options ) {
				var visible = false;
				if ( ! (options instanceof Array) || ! options.length  ) {
					visible = true;
				} else {
					array.forEach( options, function( option ) {
						if ( array.indexOf(activeOptions, option) != -1 ) {
							visible = true;
						}
					} );
				}
				var iwidget = this._form.getWidget( prop );
				if (iwidget) {
					iwidget.set( 'visible' , visible );
				}
			} ) );

			// hide/show title panes
			this._visibilityTitlePanes( this._layoutMap );
		},

		_anyVisibleWidget: function( titlePane ) {
			var visible = false;
			array.forEach( titlePane.layout, lang.hitch( this, function( element ) {
				if ( element instanceof Array ) {
					array.forEach( element, lang.hitch( this, function( property ) {
						if ( property in this._form._widgets ) {
							if ( this._form._widgets[ property ].get( 'visible' ) === true ) {
								visible = true;
								return false;
							}
						}
					} ) );
					// if there is a visible widget there is no need to check the other widgets
					if ( visible ) {
						return false;
					}
				} else if ( typeof element == "object" ) {
					if ( this._anyVisibleWidget( element ) ) {
						domClass.toggle( element.$refTitlePane$.domNode, 'dijitHidden', false );
						visible = true;
						return false;
					} else {
						domClass.toggle( element.$refTitlePane$.domNode, 'dijitHidden', true );
					}
				}
			} ) );

			return visible;
		},

		_visibilityTitlePanes: function( layout ) {
			array.forEach( layout, lang.hitch( this, function( tab ) {
				if ( typeof tab == "object" ) {
					var visible = false;
					array.forEach( tab.layout, lang.hitch( this, function( element ) {
						if ( element instanceof Array ) {
							// ignore for now
							visible = true;
							return;
						}
						if ( this._anyVisibleWidget( element ) ) {
							domClass.toggle( element.$refTitlePane$.domNode, 'dijitHidden', false );
							visible = true;
						} else {
							domClass.toggle( element.$refTitlePane$.domNode, 'dijitHidden', true );
						}
					} ) );
					if ( ! visible ) {
						this._tabs.hideChild( tab.$refSubTab$ );
					} else {
						this._tabs.showChild( tab.$refSubTab$ );
					}
				}
			} ) );
		},

		validateChanges: function(e) {
			// summary:
			//		Validate the user input through the server and save changes upon success.

			// prevent standard form submission
			e.preventDefault();

			// get all values that have been altered
			var vals = this.getAlteredValues();

			// copy dict and remove the ID
			var valsNoID = lang.mixin({}, vals);
			delete valsNoID[this.moduleStore.idProperty];

			// reset changed headings
			array.forEach(this._detailPages, function(ipage) {
				// reset the original title (in case we altered it)
				if (ipage.$titleOrig$) {
					ipage.set('title', ipage.$titleOrig$);
					delete ipage.$titleOrig$;
				}
			});

			// reset settings from last validation
			tools.forIn(this._form._widgets, function(iname, iwidget) {
				if (iwidget.setValid) {
					iwidget.setValid(null);
				}
			}, this);

			// check whether all required properties are set
			var errMessage = '' + _('The following properties need to be specified or are invalid:') + '<ul>';
			var allValuesGiven = true;
			tools.forIn(this._form._widgets, function(iname, iwidget) {
				// ignore widgets that are not visible
				if (!iwidget.get('visible')) {
					return true;
				}

				// in multi-edit mode, ignore widgets that are not marked to be overwritten
				if (this._multiEdit && (!iwidget.$refOverwrite$ || !iwidget.$refOverwrite$.get('value'))) {
					return true;
				}

				// check whether a required property is set or a property is invalid
				var tmpVal = json.stringify(iwidget.get('value'));
				var isEmpty = tmpVal == '""' || tmpVal == '[]' || tmpVal == '{}';
				if ((isEmpty && iwidget.required) || (!isEmpty && iwidget.isValid && false === iwidget.isValid())) {
					// value is empty
					allValuesGiven = false;
					errMessage += '<li>' + iwidget.label + '</li>';
					this._setWidgetInvalid(iname);
				}
			}, this);
			errMessage += '</ul>';

			// check whether any changes are made at al
			var nChanges = 0;
			var regKey = /\$.*\$/;
			tools.forIn(vals, function(ikey) {
				if (!regKey.test(ikey) || ikey == '$options$') {
					// key does not start and end with '$' and is thus a regular key
					++nChanges;
				}
			});
			tools.forIn(this._policyWidgets, function(ipolicyType, iwidgets) {
				var ival = iwidgets.$policy$.get('value');
				var iresetValue = iwidgets.$policy$._resetValue;
				if (iresetValue != ival) {
					++nChanges;
				}
			}, this);

			if (!nChanges) {
				dialog.alert(_('No changes have been made.'));
				return;
			}

			// print out an error message if not all required properties are given
			if (!allValuesGiven) {
				dialog.alert(errMessage);
				return;
			}

			// before storing the values, make a syntax check of the user input on the server side
			var valsNonEmpty = {};
			tools.forIn(valsNoID, function(ikey, ival) {
				var tmpVal = json.stringify(ival);
				var isEmpty = tmpVal == '""' || tmpVal == '[]' || tmpVal == '{}';
				if (!isEmpty) {
					valsNonEmpty[ikey] = ival;
				}
			});
			var params = {
				objectType: this._editedObjType,
				properties: valsNonEmpty
			};
			this.standby(true);
			this.umcpCommand('udm/validate', params).then(lang.hitch(this, function(data) {
				// if all elements are valid, save element
				if (this._parseValidation(data.result)) {
					this.saveChanges(vals);
				} else {
					this.standby(false);
				}
			}), lang.hitch(this, function() {
				this.standby(false);
			}));
		},

		_parseValidation: function(validationList) {
			// summary:
			//		Parse the returned data structure from validation/put/add and check
			//		whether all entries could be validated successfully.

			var allValid = true;
			var errMessage = _('The following properties could not be validated:') + '<ul>';
			array.forEach(validationList, function(iprop) {
				// make sure the form element exists
				var iwidget = this._form._widgets[iprop.property];
				if (!iwidget) {
					return true;
				}

				// iprop.valid and iprop.details may be arrays for properties with
				// multiple values... set all 'true' values to 'null' in order to reset
				// the original items validation mechanism
				var iallValid = iprop.valid;
				var ivalid = iprop.valid === true ? null : iprop.valid;
				if (ivalid instanceof Array) {
					for (var i = 0; i < ivalid.length; ++i) {
						iallValid = iallValid && ivalid[i];
						ivalid[i] = ivalid[i] === true ? null : ivalid[i];
					}
				}
				allValid = allValid && iallValid;

				// check whether form element is valid
				iwidget.setValid(ivalid, iprop.details);
				if (!iallValid) {
					this._setWidgetInvalid(iprop.property);

					// update the global error message
					errMessage += '<li>' + _("%(attribute)s: %(message)s\n", {
						attribute: iwidget.label,
						message: iprop.details || _('Error')
					}) + '</li>';
				}
			}, this);
			errMessage += '</ul>';

			if (!allValid) {
				// upon error, show error message
				dialog.alert(errMessage);
			}

			return allValid;
		},

		_setWidgetInvalid: function(name) {
			// get the widget
			var widget = this._form.getWidget(name);
			if (!widget) {
				return;
			}

			// mark the title of the subtab (in case we have not done it already)
			var page = this._propertySubTabMap[name];
			if (page && !page.$titleOrig$) {
				// store the original title
				page.$titleOrig$ = page.title;
				page.set('title', '<span style="color:red">' + page.title + ' (!)</span>');
			}
		},

		saveChanges: function(vals) {
			// summary:
			//		Save the user changes for the edited object.

			var deferred = null;
			if (this._multiEdit) {
				// save the changes for each object once
				var transaction = this.moduleStore.transaction();
				array.forEach(this.ldapName, function(idn) {
					// shallow copy with corrected DN
					var ivals = lang.mixin({}, vals);
					ivals[this.moduleStore.idProperty] = idn;
					this.moduleStore.put(ivals);
				}, this);
				deferred = transaction.commit();
			} else if (this.newObjectOptions) {
				deferred = this.moduleStore.add(vals, this.newObjectOptions);
			} else {
				deferred = this.moduleStore.put(vals);
			}
			deferred.then(lang.hitch(this, function(result) {
				// see whether saving was successfull
				this.standby(false);
				var success = true;
				var msg = '';
				if (result instanceof Array) {
					msg = '<p>' + _('The following UDM objects could not be saved:') + '</p><ul>';
					array.forEach(result, function(iresult) {
						success = success && iresult.success;
						if (!iresult.success) {
							msg += lang.replace('<li>{' + this.moduleStore.idProperty + '}: {details}</li>', iresult);
						}
					}, this);
					msg += '</ul>';
				} else {
					success = result.success;
					if (!result.success) {
						msg = _('The UDM object could not be saved: %(details)s', result);
					}
				}

				if (success) {
					// everything ok, close page
					this.onCloseTab();
					this.onSave(result.$dn$, this.objectType);
				} else {
					// print error message to user
					dialog.alert(msg);
				}
			}), lang.hitch(this, function() {
				this.standby(false);
			}));
		},

		getAlteredValues: function() {
			// summary:
			//		Return a list of object properties that have been altered.

			// get all form values and see which values are new
			var vals = this.getValues();
			var newVals = {};
			if (this._multiEdit) {
				// in multi-edit mode, get all marked entries
				tools.forIn(this._form._widgets, lang.hitch(this, function(iname, iwidget) {
					if (iwidget.$refOverwrite$ && iwidget.$refOverwrite$.get('value')) {
						newVals[iname] = iwidget.get('value');
					}
				}));
			} else if (this.newObjectOptions) {
				// get only non-empty values or values of type 'boolean'
				tools.forIn(vals, lang.hitch(this, function(iname, ival) {
					if (typeof(ival) == 'boolean' || (!(ival instanceof Array && !ival.length) && ival)) {
						newVals[iname] = ival;
					}
				}));
			} else {
				// existing object .. get only the values that changed
				tools.forIn(vals, function(iname, ival) {
					var oldVal = this._receivedObjFormData[iname];

					// check whether old values and new values differ...
					if (!tools.isEqual(ival,oldVal)) {
						newVals[iname] = ival;
					}
				}, this);

				// set the LDAP DN
				newVals[this.moduleStore.idProperty] = vals[this.moduleStore.idProperty];
			}
			return newVals;
		},

		onCloseTab: function() {
			// summary:
			//		Event is called when the page should be closed.
			return true;
		},

		onSave: function(dn, objectType) {
			// event stub
		}
	});
});


