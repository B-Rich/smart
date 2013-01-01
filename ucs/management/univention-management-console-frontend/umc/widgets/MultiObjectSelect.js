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
/*global define require */

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/aspect",
	"dojo/when",
	"dojo/store/DataStore",
	"umc/tools",
	"umc/widgets/ContainerWidget",
	"umc/widgets/_FormWidgetMixin",
	"umc/widgets/Button",
	"umc/widgets/MultiSelect",
	"umc/widgets/LabelPane",
	"umc/i18n!umc/app"
], function(declare, lang, array, aspect, when, DataStore, tools, ContainerWidget, _FormWidgetMixin, Button, MultiSelect, LabelPane, _) {

	// lazy defining of the dialog in order to avoid circular dependencies with umc/render
	var DetailDialog = declare(null, {});
	require([
		"dijit/Dialog",
		"umc/widgets/StandbyMixin",
		"umc/widgets/SearchForm"
	], function(Dialog, StandbyMixin, SearchForm) {
		DetailDialog = declare([ Dialog, StandbyMixin ], {
			widgets: [],

			queryCommand: '',

			queryOptions: {},

			autoSearch: true,

			'class': 'umcMultiObjectSelectDetailDialog',

			_form: null,

			_multiSelect: null,

			_container: null,

			uninitialize: function() {
				// make sure that the container widget is destroyed correctly
				this._container.destroyRecursive();
			},

			postMixInProperties: function() {
				this.inherited(arguments);
				if (!this.title) {
					this.title = _('Add objects');
				}
			},

			buildRendering: function() {
				this.inherited(arguments);

				// create a container for all widgets
				this._container = new ContainerWidget({});
				this._container.placeAt(this.containerNode);

				// for the layout, all Elements should be below each other
				var layout = array.map(this.widgets, function(iwidget) {
					return iwidget.name;
				});
				this._form = new SearchForm({
					widgets: this.widgets,
					layout: layout,
					onSearch: lang.hitch(this, 'search'),
					onValuesInitialized: lang.hitch(this, function() {
						// trigger the search if autoSearch is specified and as soon as all form
						// elements have been initialized
						if (this.autoSearch) {
							this.search(this._form.get('value'));
						}
					})
				});
				this._container.addChild(this._form);

				// for visualizing the search results, use a MultiSelect
				this._multiSelect = new MultiSelect({
					height: '250px',
					label: _('Search results:')
				});
				this._container.addChild(new LabelPane({
					content: this._multiSelect,
					style: 'display: block;' // do not allow for floating
				}));

				// add the final buttons to close the dialog
				this._container.addChild(new Button({
					label: _('Add'),
					iconClass: 'umcIconAdd',
					style: 'float: right;',
					onClick: lang.hitch(this, function() {
						// get all elements an trigger onAdd event
						var ids = this._multiSelect.get('value');
						if (ids.length) {
							// only trigger event if there are more then 0 entries
							this.onAdd(ids);
						}

						// hide the dialog
						this.hide();

						// unselect all elements
						this._multiSelect.selection.clear();
					})
				}));
				this._container.addChild(new Button({
					label: _('Cancel'),
					defaultButton: true,
					onClick: lang.hitch(this, function() {
						// hide the dialog
						this.hide();

						// unselect all elements
						this._multiSelect.selection.clear();

					})
				}));

				// put focus to last widget in the SearchForm
				this.on('focus', lang.hitch(this, function() {
					if (this.widgets.length) {
						var lastConf = this.widgets[this.widgets.length - 1];
						var lastName = lastConf.id || lastConf.name;
						var widget = this._form.getWidget(lastName);
						if (lang.getObject('focus', false, widget)) {
							widget.focus();
						}
					}
				}));
			},

			search: function(_values) {
				// set dynamicOptions which will trigger a reload
				var values = lang.mixin({}, this.queryOptions, _values);
				this._multiSelect.set('dynamicOptions', values);

				if (!this._multiSelect.dynamicValues) {
					// the first time we need to set dynamicValues
					this._multiSelect.set('dynamicValues', this.queryCommand);
				}
			},

			onAdd: function(ids) {
				// event stub
			}
		});
	});

	return declare("umc.widgets.MultiObjectSelect", [ ContainerWidget, _FormWidgetMixin ], {
		// summary:
		//		???

		queryWidgets: [],

		queryCommand: '',

		queryOptions: {},

		// 'javascript:functionName'
		// function(ids) { ... }
		// may return Deferred
		formatter: function(ids) {
			return array.map(ids, function(id) {
				if (typeof id == "string") {
					return {label: id, id: id};
				}
				return id;
			});
		},

		// autoSearch: String
		//	  Specifies whether or not a query is executed as soon as the dialog is
		//	  opened for the first time.
		autoSearch: true,

		// dialogTitle: String
		//	  Specifies the title of the dialog to add new entries.
		dialogTitle: null,

		name: '',

		value: null,

		// the widget's class name as CSS class
		'class': 'umcMultiObjectSelect',

		// internal reference to the parsed formatter function
		_formatter: function(ids) { return ids; },

		// object store adapter for the data store of the MultiSelect widget
		_objectStore: null,

		// reference to the MultiSelect widget
		_multiSelect: null,

		// reference to the detail dialog
		_detailDialog: null,

		// encapsulate the data store fo the multi select widget
		postMixInProperties: function() {
			this.inherited(arguments);

			// in case 'value' is not specified, generate a new array
			if (!(this.value instanceof Array)) {
				this.value = [];
			}

			// convert 'formatter' to a function
			this._formatter = tools.stringOrFunction(this.formatter);
		},

		_attachObjectStore: function() {
			this._objectStore = new DataStore( {
				store: this._multiSelect.store
			} );
		},

		buildRendering: function() {
			this.inherited(arguments);

			// add the MultiSelect widget
			this._multiSelect = new MultiSelect({});
			this._attachObjectStore();
			if ( 'setStore' in this._multiSelect ) {
				this.own(aspect.after(this._multiSelect, 'setStore', lang.hitch(this, '_attachObjectStore')));
			}
			var container = new ContainerWidget({});
			container.addChild(this._multiSelect);
			this.addChild(container);

			// add the Buttons
			container = new ContainerWidget({});
			container.addChild(new Button({
				label: _('Add'),
				iconClass: 'umcIconAdd',
				onClick: lang.hitch(this, function() {
					if (!this._detailDialog) {
						// dialog does not exist, create a new one
						this._detailDialog = new DetailDialog({
							widgets: this.queryWidgets,
							queryCommand: lang.hitch( this, 'queryCommand' ),
							queryOptions: this.queryOptions || {},
							autoSearch: this.autoSearch,
							title: this.dialogTitle
						});

						// register the event handler
						this._detailDialog.on('add', lang.hitch(this, '_addElements'));
						this.onCreateDialog( this._detailDialog );
					}
					this.onShowDialog( this._detailDialog );
					this._detailDialog.show();
				})
			}));
			container.addChild(new Button({
				label: _('Remove'),
				iconClass: 'umcIconDelete',
				onClick: lang.hitch(this, '_removeSelectedElements'),
				style: 'float: right;'
			}));
			this.addChild(container);
		},

		_setValueAttr: function(_values) {
			// handle possible Deferred object returned by the formatter
			when(this._formatter(_values), lang.hitch(this, function(values) {
				// sort the array according to the labels
				values.sort(tools.cmpObjects('label'));

				// callback handler
				this._multiSelect.set('staticValues', values);

				// notify observers
				this._set('value', values);
			}));
		},

		_getValueAttr: function() {
			// return a copy
			var values = [];
			this._objectStore.query( {} ).map( function( item ) {
				values.push( item.id );
			} );
			return values;
		},

		getQueryWidget: function(name) {
			// summary:
			//		Return the widget according to the specified name.
			return this._detailDialog._form.getWidget(name);
		},

		getAllItems: function() {
			return this._multiSelect.getAllItems();
		},

		_addElements: function( ids ) {
			// only add elements that do not exist already
			var dialog_store = new DataStore( { store: this._detailDialog._multiSelect.store } );
			var elements = [];
			array.forEach( ids.concat(this.get('value')) , lang.hitch( this, function( id ) {
				var item;
				try {
					item = this._objectStore.get( id );
				} catch( e ) {
					// object does not exist, so we add it ...
					item = dialog_store.get( id );
				}
				if(-1 === array.indexOf(elements, item)) {
					elements.push(item);
				}
			} ) );
			this.set('value', elements);
		},

		_removeSelectedElements: function() {
			// create a dict for all selected elements
			var values = this.get('value');
			array.forEach(this._multiSelect.getSelectedItems(), lang.hitch( this, function( iid ) {
				values.splice(array.indexOf(values, iid.id), 1);
			} ) );
			var elements = [];
			array.forEach(values, lang.hitch(this, function(id) {
				elements.push(this._objectStore.get(id));
			}));
			this._multiSelect.selection.clear();
			this.set('value', elements);
		},

		uninitialize: function() {
			if (this._detailDialog) {
				this._detailDialog.destroy();
			}
		},

		onCreateDialog: function( dialog ) {
			// event stub
		},

		onShowDialog: function( dialog ) {
			// event stub
		}
	});
});

