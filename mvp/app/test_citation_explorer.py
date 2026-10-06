import json
import unittest
import db
import dashboard
import citation_explorer as ce
import citation_panel
import insight_panels
import test_dashboard


class CitationExplorerTests(unittest.TestCase):
    setUp = test_dashboard.DashboardTests.setUp
    tearDown = test_dashboard.DashboardTests.tearDown

    def context(self, query=None):
        s,ps,p=dashboard.context('test',query or {})
        return insight_panels.period_context(ps,p,query or {}),p

    def citations(self, aid, rows):
        db.write('UPDATE answers SET citations=? WHERE id=?',(json.dumps(rows),aid))

    def test_url_per_answer_not_annotation_count(self):
        self.citations(1,[{'url':'https://www.example.com/products/cleanser?utm_source=ai','title':'Cleanser'},
                          {'url':'https://example.com/products/cleanser?utm_medium=ai'},
                          {'url':'javascript:alert(1)'},None])
        self.citations(2,[{'url':'https://example.com/products/cleanser'}])
        ctx,p=self.context()
        rows,_=ce.records(ctx,p)
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r['domain']=='example.com' for r in rows))
        self.assertEqual(rows[0]['order'],1)
        self.assertNotIn('utm_',rows[0]['url'])
        self.assertEqual(ce.content_type('https://example.com/mystery'),'Unclassified')

    def test_product_relationship_is_specific_to_answer(self):
        db.write("UPDATE mentions SET url='https://retailer.test/item/cleanser' WHERE is_theirs=1")
        for aid in [1,2]:
            self.citations(aid,[{'url':'https://retailer.test/item/cleanser'}])
        ctx,p=self.context()
        rows,_=ce.records(ctx,p)
        self.assertEqual([r['relation'] for r in rows],['Other listing of your product','Other source'])
        sources,_=citation_panel.evidence(ctx['ids'],p)
        self.assertEqual(len(sources[0]['answers']),1)

    def test_models_period_and_processing_filters(self):
        db.write("UPDATE answers SET engine='perplexity' WHERE id=2")
        for aid in [1,2]:
            self.citations(aid,[{'url':'https://example.com/article/source'}])
        ctx,p=self.context({'engines':'perplexity'})
        rows,_=ce.records(ctx,p)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['model'],'Perplexity')
        db.write("UPDATE answer_processing SET status='pending' WHERE answer_id=2")
        ctx,p=self.context({'engines':'perplexity'})
        self.assertEqual(ce.records(ctx,p)[0],[])
        ctx,p=self.context({'range':'custom','from':'2020-01-01','to':'2020-02-01'})
        self.assertEqual(ce.records(ctx,p)[0],[])

    def test_embedded_citation_titles_are_not_executable(self):
        self.citations(1,[{'url':'https://example.com/page','title':'</script><script>alert(1)</script>'}])
        ctx,p=self.context()
        html=ce.render({'token':'test'},ctx,p)
        self.assertNotIn('</script><script>alert(1)</script>',html)
        self.assertIn('\\u003c/script>',html)


if __name__=='__main__':
    unittest.main()
