# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Devtest web admin views.
"""

from __future__ import generator_stop

from gettext import gettext

from flask import flash

from peewee import Field

from wtfpeewee.orm import ModelConverter, model_form

from flask_admin import Admin, parse_like_term
from flask_admin.menu import MenuLink
from flask_admin.form import BaseForm
from flask_admin.model import BaseModelView
from flask_admin.contrib.peewee import filters
from flask_admin.model.ajax import AjaxModelLoader, DEFAULT_PAGE_SIZE

from devtest.db import models
from devtest.db import fields

from . import fields as formfields


class QueryAjaxModelLoader(AjaxModelLoader):
    def __init__(self, name, model, **options):
        super().__init__(name, options)

        self.model = model
        self.fields = options.get('fields')

        if not self.fields:
            raise ValueError(
                'AJAX loading requires `fields` '
                'to be specified for {}.{}'.format(model, self.name))

        self._cached_fields = self._process_fields()

        self.pk = model._meta.primary_key.name

    def _process_fields(self):
        remote_fields = []

        for field in self.fields:
            if isinstance(field, str):
                attr = getattr(self.model, field, None)

                if not attr:
                    raise ValueError('%s.%s does not exist.' % (self.model, field))

                remote_fields.append(attr)
            else:
                remote_fields.append(field)

        return remote_fields

    def format(self, model):
        if not model:
            return None

        return (getattr(model, self.pk), str(model))

    def get_one(self, pk):
        return self.model.get(**{self.pk: pk})

    def get_list(self, term, offset=0, limit=DEFAULT_PAGE_SIZE):
        query = self.model.select()

        stmt = None
        for field in self._cached_fields:
            q = field ** ('%%{}%%'.format(term))

            if stmt is None:
                stmt = q
            else:
                stmt |= q

        query = query.where(stmt)
        query = query.paginate(offset + 1, limit)
        return list(query.execute())


def create_ajax_loader(model, name, field_name, options):
    prop = getattr(model, field_name, None)

    if prop is None:
        raise ValueError('Model {!r} does not have field {!r}.'.format(model.__name__, field_name))

    remote_model = prop.model
    return QueryAjaxModelLoader(name, remote_model, **options)


class ModelView(BaseModelView):

    column_list = None
    # column_filters = None
    column_searchable_list = None
    filter_converter = filters.FilterConverter()
    form_overrides = None
    form_exclude = None
    column_default_sort = None
    field_args = None

    def get_pk(self, model):
        return model._meta.primary_key.name

    def get_pk_value(self, modelinstance):
        return modelinstance._get_pk_value()

    def scaffold_list_columns(self):
        return self.column_list or []

    def scaffold_sortable_columns(self):
        columns = {}
        for name in self.column_list:
            columns[name] = getattr(self.model, name)
        return columns

    def init_search(self):
        self._search_fields = []
        if self.column_searchable_list:
            for p in self.column_searchable_list:
                if isinstance(p, str):
                    p = getattr(self.model, p)
                field_type = type(p)
                # Check type
                if (field_type != fields.CharField and field_type != fields.TextField):
                    raise ValueError(
                        'Can only search on text columns. '
                        'Failed to setup search for "{}"'.format(p))
                self._search_fields.append(p)

        return bool(self._search_fields)

    def is_valid_filter(self, filt):
        return isinstance(filt, filters.BasePeeweeFilter)

    def scaffold_filters(self, name):
        if isinstance(name, str):
            attr = getattr(self.model, name, None)
        else:
            attr = name
        if attr is None:
            raise ValueError('Failed to find field for filter: {}'.format(name))

        # Check if field is in different model
        if attr.model != self.model:
            visible_name = '%s / %s' % (self.get_column_name(attr.model.__name__),
                                        self.get_column_name(attr.name))
        else:
            if not isinstance(name, str):
                visible_name = self.get_column_name(attr.name)
            else:
                visible_name = self.get_column_name(name)

        type_name = type(attr).__name__
        flt = self.filter_converter.convert(type_name,
                                            attr,
                                            visible_name)
        return flt

    def scaffold_form(self):
        form_class = model_form(self.model,
                                base_class=BaseForm, allow_pk=False,
                                only=None, exclude=self.form_exclude,
                                field_args=self.field_args,
                                converter=ModelConverter(overrides=self.form_overrides))
        return form_class

#    def scaffold_list_form(self, widget=None, validators=None):
#        pass # TODO

    def _handle_join(self, query, field, joins):
        if field.model != self.model:
            model_name = field.model.__name__

            if model_name not in joins:
                query = query.join(field.model)
                joins.add(model_name)
        return query

    def _order_by(self, query, joins, sort_field, sort_desc):
        if isinstance(sort_field, str):
            field = getattr(self.model, sort_field)
            query = query.order_by(field.desc() if sort_desc else field.asc())
        elif isinstance(sort_field, Field):
            if sort_field.model != self.model:
                query = self._handle_join(query, sort_field, joins)
            query = query.order_by(sort_field.desc() if sort_desc else sort_field.asc())
        return query, joins

    def get_list(self, page, sort_field, sort_desc, search, filters,
                 page_size=20):
        """
            Return a paginated and sorted list of models from the data source.

            :param page:
                Page number, 0 based. Can be set to None if it is first page.
            :param sort_field:
                Sort column name or None.
            :param sort_desc:
                If set to True, sorting is in descending order.
            :param search:
                Search query
            :param filters:
                List of filter tuples. First value in a tuple is a search
                index, second value is a search value.
            :param page_size:
                Number of results. Defaults to ModelView's page_size. Can be
                overriden to change the page_size limit. Removing the page_size
                limit requires setting page_size to 0 or False.
        """

        joins = set()

        query = self.model.select()

        # Search
        if search:
            values = search.split(' ')

            for value in values:
                if not value:
                    continue

                term = parse_like_term(value)

                stmt = None
                for field in self._search_fields:
                    query = self._handle_join(query, field, joins)

                    q = field ** term

                    if stmt is None:
                        stmt = q
                    else:
                        stmt |= q

                query = query.where(stmt)

        # Filters
        # TODO filters

        # Get count
        count = query.count()

        # Apply sorting
        if sort_field is not None:
            f = getattr(self.model, sort_field)
            query = query.order_by(-f) if sort_desc else query.order_by(f)
            # query, joins = self._order_by(query, joins, sort_field, sort_desc)
        else:
            order = self._get_default_order()
            if order:
                query, joins = self._order_by(query, joins, order[0], order[1])

        # Pagination
        query = query.paginate(page + 1, page_size)

        return count, list(query.execute())

    def get_one(self, id):
        return self.model.get(self.model.id == int(id))

    def create_model(self, form):
        try:
            row = self.model()
            form.populate_obj(row)
            row.save()
        except Exception as ex:
            if not self.handle_view_exception(ex):
                flash(gettext('Failed to create record. %(error)s', error=str(ex)), 'error')
            return False
        else:
            self.after_model_change(form, row, True)
        return row

    def update_model(self, form, row):
        try:
            form.populate_obj(row)
            row.save()
        except Exception as ex:
            if not self.handle_view_exception(ex):
                flash(gettext('Failed to update record. %(error)s', error=str(ex)), 'error')
            return False
        else:
            self.after_model_change(form, row, False)
        return True

    def delete_model(self, row):
        try:
            self.on_model_delete(row)
            row.delete_instance(recursive=True)
        except Exception as ex:
            if not self.handle_view_exception(ex):
                flash(gettext('Failed to delete record. %(error)s', error=str(ex)), 'error')
            return False
        else:
            self.after_model_delete(row)
        return True

    def _create_ajax_loader(self, name, options):
        return create_ajax_loader(self.model, name, name, options)


class FunctionView(ModelView):
    column_list = ("name", "description")
    column_default_sort = 'name'

    def __init__(self):
        super().__init__(models.Function, category="Software")


class RadarComponentView(ModelView):
    column_list = ("name", "version")
    column_default_sort = 'name'

    def __init__(self):
        super().__init__(models.RadarComponent, category="Misc")


class EquipmentModelView(ModelView):
    column_list = ("manufacturer", "name")
    form_overrides = dict(attributes=formfields.JSONField)
    can_view_details = True
    column_details_list = column_list + ("note", "specs", "radar_component",
                                         "attributes")

    def __init__(self):
        super().__init__(models.EquipmentModel, category="Testbeds")


class EquipmentView(ModelView):
    column_list = ("model", "name", "serno")
    form_overrides = dict(attributes=formfields.JSONField)
    inline_models = (models.Interfaces,)
    can_view_details = True
    column_details_list = column_list + ("account", "user", "location", "notes",
                                         "partof", "attributes", "active")
    # column_editable_list = ("location", "active")
    form_ajax_refs = {
        'account': {
            'fields': ('identifier', 'login', 'password', 'admin'),
            'page_size': 10
        },
        'user': {
            'fields': ('identifier', 'login', 'password', 'admin'),
            'page_size': 10
        }
    }

    def __init__(self):
        super().__init__(models.Equipment, category="Testbeds")


class InterfacesView(ModelView):
    column_list = ("name", "macaddr", "ipaddr", "ipaddr6")
    can_view_details = True
    column_details_list = column_list + ("alias", "status", "vlan",
                                         "parent", "equipment", "network")
    form_overrides = dict(ipaddr=formfields.IPv4Field,
                          ipaddr6=formfields.IPv6Field,
                          macaddr=formfields.MACField)

    def __init__(self):
        super().__init__(models.Interfaces, category="Testbeds")


class NetworksView(ModelView):
    column_list = ("name", "type", "ipnetwork", "ip6network")
    can_view_details = True
    column_details_list = column_list + ("layer", "vlanid", "lower", "notes",
                                         "attributes")
    form_overrides = dict(ipnetwork=formfields.CIDRField,
                          ip6network=formfields.CIDRField,
                          attributes=formfields.JSONField,
                          type=formfields.EnumField,
                          )
    field_args = dict(type={"choices": models.Networks.type.choices})

    def __init__(self):
        super().__init__(models.Networks, category="Testbeds")


class ConnectionView(ModelView):
    column_list = ("source", "destination", "type", "state")
    form_overrides = dict(type=formfields.EnumField)
    field_args = dict(type={"choices": models.Connection.type.choices})

    def __init__(self):
        super().__init__(models.Connection, category="Testbeds")


class TestBedView(ModelView):
    column_list = ("name",)
    form_overrides = dict(attributes=formfields.JSONField)

    def __init__(self):
        super().__init__(models.TestBed, category="Testbeds")


class TestequipmentView(ModelView):
    column_list = ("testbed", "equipment")

    def __init__(self):
        super().__init__(models.Testequipment, category="Testbeds")


class AccountIdsView(ModelView):
    column_list = ("identifier",)

    def __init__(self):
        super().__init__(models.AccountIds, category="Testbeds")


class SoftwareVariantView(ModelView):
    column_list = ("name",)

    def __init__(self):
        super().__init__(models.SoftwareVariant, category="Software")


class SoftwareView(ModelView):
    column_list = ("name", "version")
    form_overrides = dict(attributes=formfields.JSONField)

    def __init__(self):
        super().__init__(models.Software, category="Software")


class ProjectBuildView(ModelView):

    def __init__(self):
        super().__init__(models.ProjectBuild, category="Software")


class TestCaseView(ModelView):
    column_list = ("name", "purpose", "testimplementation")
    form_exclude = ("owners", "related_problems")
    column_details_list = (column_list +
                           ("passcriteria", "startcondition", "endcondition",
                            "procedure", "attributes", "comments", "type",
                            "priority", "status", "interactive", "automated",
                            "target_software", "target_component",
                            "radar_component", "time_estimate", "lastchange",
                            "valid"))

    form_overrides = dict(purpose=formfields.HTMLField,
                          attributes=formfields.JSONField,
                          type=formfields.EnumField,
                          priority=formfields.EnumField,
                          status=formfields.EnumField,
                          time_estimate=formfields.IntervalField,
                          # owners=formfields.ArrayField,
                          # related_problems=formfields.ArrayField,
                          )
    field_args = dict(type={"choices": models.TestCases.type.choices},
                      priority={"choices": models.TestCases.priority.choices},
                      status={"choices": models.TestCases.status.choices},
                      )
    can_view_details = True

    def __init__(self):
        super().__init__(models.TestCases, category="Tests")


class TestSuiteView(ModelView):
    column_list = ("name", "purpose", "suiteimplementation")
    form_exclude = ("owners", "test_cases")
    column_details_list = column_list + ("lastchange", "valid")
    form_overrides = dict(purpose=formfields.HTMLField,
                          # owners=formfields.ArrayField,
                          # test_cases=formfields.ArrayField,
                          )
    can_edit = False
    can_view_details = True

    def __init__(self):
        super().__init__(models.TestSuites, category="Tests")


class ScenarioView(ModelView):
    column_list = ("name", "purpose", "implementation")
    form_exclude = ("owners",)
    column_details_list = column_list + ("parameters", "reportname", "notes",
                                         "testbed", "testsuite")
    form_overrides = dict(purpose=formfields.HTMLField,
                          parameters=formfields.JSONField,
                          # owners=formfields.ArrayField,
                          )
    can_edit = False
    can_view_details = True

    def __init__(self):
        super().__init__(models.Scenario, category="Tests")


class TestResultsView(ModelView):
    column_list = ("testcase", "testsuite", "resulttype", "result")
    form_exclude = ("owners",)
    column_details_list = column_list + ("arguments", "parent",
                                         "starttime", "endtime", "diagnostic",
                                         "rdb_uuid", "resultslocation", "testversion",
                                         "target", "dutbuild",
                                         "note", "valid")
    form_overrides = dict(data=formfields.JSONField,
                          result=formfields.EnumField,
                          resulttype=formfields.EnumField,
                          rdb_uuid=formfields.UUIDField,
                          )
    field_args = dict(result={"choices": models.TestResults.result.choices},
                      resulttype={"choices": models.TestResults.resulttype.choices},
                      )
    can_edit = False
    can_create = False
    can_view_details = True

    def __init__(self):
        super().__init__(models.TestResults, category="Tests")


def initialize_app(app, home_endpoint=None):
    models.connect()

    @app.before_request
    def _db_connect():
        models.database.connect()

    @app.teardown_request
    def _db_close(exc):
        if not models.database.is_closed():
            models.database.commit()
            models.database.close()

    admin = Admin(app, name='Raw Table Admin', template_mode='bootstrap3')

    if home_endpoint:
        admin.add_link(MenuLink("Devtest Main", url="/", endpoint=home_endpoint))

    admin.add_views(TestBedView(),
                    EquipmentModelView(),
                    EquipmentView(),
                    NetworksView(),
                    InterfacesView(),
                    ConnectionView(),
                    AccountIdsView(),
                    TestequipmentView())
    admin.add_views(SoftwareView(),
                    SoftwareVariantView(),
                    FunctionView())
    admin.add_views(ScenarioView(),
                    TestSuiteView(),
                    TestCaseView(),
                    TestResultsView())
    admin.add_view(RadarComponentView())


def _test(argv):
    fmv = FunctionView()
    print(fmv)


if __name__ == "__main__":
    import sys
    _test(sys.argv)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab:fileencoding=utf-8
